"""
test_txt_reconstruction_engine.py — Test suite for Deterministic TXT Reconstruction Engine.

Verifies:
1. Intact TXT evidence (100% verified, 0 reconstructed, 0 missing, FULLY_RECOVERED, exact match).
2. Truncated UTF-8 tail sequence (tail trimmed, missing_bytes > 0, PARTIALLY_RECOVERED).
3. Corrupted UTF-8 bytes in middle (invalid bytes repaired into '?', PARTIALLY_RECOVERED).
4. Null / noise byte padded evidence (null runs stripped/normalized, PARTIALLY_RECOVERED).
5. Fragmented TXT evidence (multi-block text recovery).
6. Unrecoverable binary garbage evidence (UNRECOVERABLE, success=False).
7. SHA-256 ground truth verification (exact match detection).
8. End-to-End API upload and download (/api/recover-file & download endpoint).
"""

from __future__ import annotations

import hashlib
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.recovery.reconstructors.txt import reconstruct_txt
from backend.app.recovery.signatures import SYNTHETIC_START_MARKER, SYNTHETIC_END_MARKER
from backend.app.models.reconstruction import ReconstructionResult


client = TestClient(app)


def test_1_intact_txt_evidence():
    """1. Intact TXT: 100% verified, 0 reconstructed, 0 missing, FULLY_RECOVERED."""
    intact_text = b"Recoverix Forensic Evidence File\nStatus: Verified Intact\n"
    res = reconstruct_txt(intact_text, ground_truth=intact_text)

    assert isinstance(res, ReconstructionResult)
    assert res.format == "txt"
    assert res.status == "FULLY_RECOVERED"
    assert res.success is True
    assert res.verified_bytes == len(intact_text)
    assert res.reconstructed_bytes == 0
    assert res.missing_bytes == 0
    assert len(res.recovered_bytes) == len(intact_text)
    assert res.is_exact_match is True
    # Invariant: total = verified + reconstructed + missing
    assert len(intact_text) == res.verified_bytes + res.reconstructed_bytes + res.missing_bytes


def test_2_truncated_utf8_tail():
    """2. Truncated UTF-8 tail: Multi-byte sequence cut off at end."""
    valid_prefix = b"Forensic Trace Log: User Action "
    # Multi-byte UTF-8 char for '€' is b"\xe2\x82\xac" (3 bytes)
    # Truncate to just the first byte b"\xe2"
    damaged_input = valid_prefix + b"\xe2"

    res = reconstruct_txt(damaged_input)

    assert res.format == "txt"
    assert res.status == "PARTIALLY_RECOVERED"
    assert res.success is True
    assert res.missing_bytes == 1  # 1 truncated tail byte cut off
    assert res.verified_bytes == len(valid_prefix)
    assert res.reconstructed_bytes == 0
    assert len(damaged_input) == res.verified_bytes + res.reconstructed_bytes + res.missing_bytes
    assert "TRUNCATED_TAIL_TRIM" in res.reconstruction_methods
    assert res.is_exact_match is False


def test_3_corrupted_utf8_bytes_in_middle():
    """3. Corrupted UTF-8 bytes: Invalid sequence in middle replaced with '?'."""
    part1 = b"System log entry: "
    bad_bytes = b"\xff\xfe\xfd"  # Invalid UTF-8 sequence (3 bytes)
    part2 = b" completed successfully."

    damaged_input = part1 + bad_bytes + part2
    res = reconstruct_txt(damaged_input)

    assert res.format == "txt"
    assert res.status == "PARTIALLY_RECOVERED"
    assert res.success is True
    assert res.verified_bytes == len(part1) + len(part2)
    assert res.reconstructed_bytes == 3  # Replaced 3 invalid bytes with 3 '?' bytes
    assert res.missing_bytes == 0  # 3 input - 3 reconstructed = 0 missing
    assert len(damaged_input) == res.verified_bytes + res.reconstructed_bytes + res.missing_bytes
    assert b"?" in res.recovered_bytes
    assert "UTF8_REPAIR" in res.reconstruction_methods


def test_4_null_and_noise_byte_runs():
    """4. Null / Noise byte runs: Null byte run scrubbed/normalized."""
    header = b"Log Start\n"
    null_noise = b"\x00" * 16
    footer = b"Log End\n"

    damaged_input = header + null_noise + footer
    res = reconstruct_txt(damaged_input)

    assert res.format == "txt"
    assert res.status == "PARTIALLY_RECOVERED"
    assert res.success is True
    assert res.verified_bytes == len(header) + len(footer)
    assert len(damaged_input) == res.verified_bytes + res.reconstructed_bytes + res.missing_bytes
    assert "GARBAGE_CLEANUP" in res.reconstruction_methods


def test_5_fragmented_txt_evidence():
    """5. Fragmented TXT evidence: Multi-block evidence with synthetic boundary markers."""
    txt_body = b"Fragment A content\nFragment B content\n"
    evidence = SYNTHETIC_START_MARKER + b"FMT:txt;" + txt_body + SYNTHETIC_END_MARKER

    res = reconstruct_txt(evidence)

    assert res.format == "txt"
    assert res.success is True
    assert res.verified_bytes > 0
    assert txt_body in res.recovered_bytes
    assert len(evidence) == res.verified_bytes + res.reconstructed_bytes + res.missing_bytes


def test_6_unrecoverable_binary_evidence():
    """6. Unrecoverable binary evidence: High entropy binary noise fails TXT reconstruction."""
    binary_noise = bytes([b for b in range(1, 32) if b not in (9, 10, 13)] * 5)
    res = reconstruct_txt(binary_noise)

    assert res.format == "txt"
    assert res.status == "UNRECOVERABLE"
    assert res.success is False
    assert res.verified_bytes == 0
    assert res.recovered_bytes == b""
    assert res.missing_bytes == len(binary_noise)


def test_7_sha256_integrity_verification():
    """7. SHA-256 integrity: Compare ground truth hash with reconstructed output."""
    ground_truth = b"Forensic Investigation Case #999\nAnalyst: Agent\n"
    res = reconstruct_txt(ground_truth, ground_truth=ground_truth)

    assert res.is_exact_match is True
    assert hashlib.sha256(res.recovered_bytes).hexdigest() == hashlib.sha256(ground_truth).hexdigest()

    # Damaged evidence with destroyed content resulting in SHA-256 mismatch
    damaged = ground_truth[:20] + b"\xff\xff\xff" + ground_truth[23:]
    res_damaged = reconstruct_txt(damaged, ground_truth=ground_truth)
    assert res_damaged.status == "PARTIALLY_RECOVERED"
    assert res_damaged.is_exact_match is False


def test_8_end_to_end_api_upload_and_download():
    """8. End-to-End API: Upload damaged file via /api/recover-file and verify download."""
    txt_payload = b"User login trace\nAction: Authenticated\n" + b"\x00" * 8 + b"Session: Active\n"
    files = {"file": ("trace.txt", txt_payload, "text/plain")}

    response = client.post("/api/recover-file", files=files)
    assert response.status_code == 200
    data = response.json()

    assert data["format"] == "txt"
    assert data["status"] in ["FULLY_RECOVERED", "PARTIALLY_RECOVERED"]
    assert data["verified_bytes"] > 0
    assert data["is_downloadable"] is True
    assert "download_url" in data

    # Test download endpoint
    dl_url = data["download_url"]
    dl_response = client.get(dl_url)
    assert dl_response.status_code == 200
    assert len(dl_response.content) > 0
    assert b"User login trace" in dl_response.content
