"""
test_recovery_truth.py — Regression test suite enforcing forensic truth and byte accounting.

Verifies the core forensic invariants across recovery scenarios:
  Case A: Intact TXT evidence (known file) -> FULLY_RECOVERED, V=orig, R=0, M=0, 0 damage regions
  Case B: Intact CSV evidence (known file) -> FULLY_RECOVERED, V=orig, R=0, M=0, 0 damage regions
  Case C: Truncated TXT (mid-line cut, missing trailing newline) -> PARTIALLY_RECOVERED, M > 0, V+R+M=input
  Case D: Truncated CSV (partial line cut) -> PARTIALLY_RECOVERED, M > 0, V+R+M=input
  Case E: Physically fragmented TXT (sparse evidence with null gap) -> PARTIALLY_RECOVERED, physical gap preserved as MISSING damage
  Case F: Physically fragmented CSV (sparse evidence with null gap) -> PARTIALLY_RECOVERED, physical gap preserved as MISSING damage
  Case G: Deterministically reconstructable artifact (structural repair R > 0) -> PARTIALLY_RECOVERED, V+R+M=budget
  Case H: Ambiguous bifragment reconstruction -> selected_gap_size is None, ambiguity preserved without arbitrary picking
  Case I: Unrecoverable binary noise/garbage -> UNRECOVERABLE, V=0, R=0, M=input, 0 reconstruction steps
  Blind Mode: In blind carving, text/csv evidence never claims FULLY_RECOVERED
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.store import store
from backend.app.models.recovery_run import RecoveryRun, DamageRegion, Fragment
from backend.app.recovery.tracer import execute_traced_recovery
from backend.app.recovery.reconstruction import (
    reconstruct_text,
    reconstruct_csv,
    reconstruct_fragment_pair,
    reconstruct_artifact,
)
from backend.app.recovery.bifragment import reconstruct_bifragment
from backend.app.recovery.validators import validate_txt, validate_csv
from backend.app.recovery.completeness import assess_artifact_completeness

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_store():
    """Clear store between tests to prevent side effects."""
    store.clear()
    yield
    store.clear()


# ── Case A: Intact TXT Evidence ─────────────────────────────────────────────

def test_case_a_intact_txt_trace_and_api():
    """Case A: Intact TXT must be reported as FULLY_RECOVERED with V=orig, R=0, M=0."""
    content = (
        b"FORENSIC INCIDENT LOG\n"
        b"Timestamp: 2026-09-28T12:00:00Z\n"
        b"Event: Normal system shutdown.\n"
        b"Status: Verified complete.\n"
    )
    total_len = len(content)

    # 1. Traced recovery execution
    run = execute_traced_recovery("incident.txt", content, detection_mode="known_file")
    assert isinstance(run, RecoveryRun)
    assert run.format == "txt"
    assert run.status == "FULLY_RECOVERED"
    assert run.total_input_bytes == total_len
    assert run.total_verified_bytes == total_len
    assert run.total_reconstructed_bytes == 0
    assert run.total_missing_bytes == 0
    assert run.total_verified_bytes + run.total_reconstructed_bytes + run.total_missing_bytes == total_len
    assert len(run.damage_regions) == 0
    assert len(run.reconstruction_steps) == 0

    # 2. REST API /api/recover-file endpoint
    resp = client.post(
        "/api/recover-file",
        files={"file": ("incident.txt", content, "text/plain")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "FULLY_RECOVERED"
    assert data["verified_bytes"] == total_len
    assert data["reconstructed_bytes"] == 0
    assert data["missing_bytes"] == 0
    assert data["confidence_score"] == 100.0
    assert data["is_downloadable"] is True


# ── Case B: Intact CSV Evidence ─────────────────────────────────────────────

def test_case_b_intact_csv_trace_and_api():
    """Case B: Intact CSV must be reported as FULLY_RECOVERED with V=orig, R=0, M=0."""
    content = (
        b"transaction_id,account,amount,status\n"
        b"TX1001,ACC-8821,1450.50,CONFIRMED\n"
        b"TX1002,ACC-4490,320.00,PENDING\n"
        b"TX1003,ACC-1102,99.95,SETTLED\n"
    )
    total_len = len(content)

    # 1. Traced recovery execution
    run = execute_traced_recovery("ledger.csv", content, detection_mode="known_file")
    assert isinstance(run, RecoveryRun)
    assert run.format == "csv"
    assert run.status == "FULLY_RECOVERED"
    assert run.total_input_bytes == total_len
    assert run.total_verified_bytes == total_len
    assert run.total_reconstructed_bytes == 0
    assert run.total_missing_bytes == 0
    assert run.total_verified_bytes + run.total_reconstructed_bytes + run.total_missing_bytes == total_len
    assert len(run.damage_regions) == 0
    assert len(run.reconstruction_steps) == 0

    # 2. REST API /api/recover-file endpoint
    resp = client.post(
        "/api/recover-file",
        files={"file": ("ledger.csv", content, "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "FULLY_RECOVERED"
    assert data["verified_bytes"] == total_len
    assert data["reconstructed_bytes"] == 0
    assert data["missing_bytes"] == 0
    assert data["confidence_score"] == 100.0
    assert data["is_downloadable"] is True


# ── Case C: Truncated TXT Evidence ──────────────────────────────────────────

def test_case_c_truncated_txt():
    """Case C: Truncated TXT (mid-line cut without newline) cannot be FULLY_RECOVERED."""
    # Complete line followed by a truncated partial line
    content = (
        b"Line 1: system audit commenced.\n"
        b"Line 2: error encountered during execution at 0x7fff882"
    )
    total_len = len(content)

    # Completeness assessment should directly flag truncation
    is_complete = assess_artifact_completeness("txt", content, detection_mode="known_file")
    assert is_complete is False

    # Recovery run must reflect partial recovery and preserve byte accounting
    run = execute_traced_recovery("notes.txt", content, detection_mode="known_file")
    assert run.status == "PARTIALLY_RECOVERED"
    assert run.status != "FULLY_RECOVERED"
    assert run.total_missing_bytes > 0
    assert run.total_verified_bytes + run.total_reconstructed_bytes + run.total_missing_bytes == total_len
    assert len(run.damage_regions) >= 1
    assert any(d.type in ("TRUNCATED", "MISSING") for d in run.damage_regions)

    # API test
    resp = client.post(
        "/api/recover-file",
        files={"file": ("notes.txt", content, "text/plain")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "PARTIALLY_RECOVERED"


# ── Case D: Truncated CSV Evidence ──────────────────────────────────────────

def test_case_d_truncated_csv():
    """Case D: Truncated CSV (cut mid-row without newline) cannot be FULLY_RECOVERED."""
    content = (
        b"id,name,role,status\n"
        b"1,alice,admin,active\n"
        b"2,bob,operator"  # Missing status column and trailing newline
    )
    total_len = len(content)

    # Completeness assessment should recognize truncated record
    is_complete = assess_artifact_completeness("csv", content, detection_mode="known_file")
    assert is_complete is False

    # Recovery run
    run = execute_traced_recovery("users.csv", content, detection_mode="known_file")
    assert run.status == "PARTIALLY_RECOVERED"
    assert run.status != "FULLY_RECOVERED"
    assert run.total_missing_bytes > 0
    assert run.total_verified_bytes + run.total_reconstructed_bytes + run.total_missing_bytes == total_len
    assert len(run.damage_regions) >= 1

    # API test
    resp = client.post(
        "/api/recover-file",
        files={"file": ("users.csv", content, "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "PARTIALLY_RECOVERED"


# ── Case E: Physically Fragmented TXT (Sparse Evidence) ────────────────────

def test_case_e_physically_fragmented_txt():
    """Case E: Physically fragmented TXT must detect the physical null gap as MISSING damage.

    Original artifact: 293 bytes
    Fragment 1: 42 bytes
    Missing physical gap: 209 bytes (filled with null bytes)
    Fragment 2: 42 bytes
    """
    frag1 = b"Server error log 2026-09-28\nStatus: Error\n"
    frag2 = b"Details: Process terminated unexpectedly.\n"
    gap = b"\x00" * 209
    content = frag1 + gap + frag2
    total_len = len(content)
    assert total_len == 293

    run = execute_traced_recovery("server.txt", content, detection_mode="known_file")
    assert run.status == "PARTIALLY_RECOVERED"
    assert run.status != "FULLY_RECOVERED"
    assert run.total_input_bytes == 293
    assert run.total_verified_bytes == 84
    assert run.total_reconstructed_bytes == 0
    assert run.total_missing_bytes == 209
    assert run.total_verified_bytes + run.total_reconstructed_bytes + run.total_missing_bytes == 293

    # Damage region must document the physical missing gap
    assert len(run.damage_regions) == 1
    damage = run.damage_regions[0]
    assert damage.type == "MISSING"
    assert damage.start_offset == 42
    assert damage.length == 209
    assert damage.end_offset == 251

    # 2 distinct fragments must be tracked
    assert len(run.fragments) == 2
    assert run.fragments[0].offset == 0
    assert run.fragments[0].length == 42
    assert run.fragments[1].offset == 251
    assert run.fragments[1].length == 42

    # API verification
    resp = client.post(
        "/api/recover-file",
        files={"file": ("server.txt", content, "text/plain")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "PARTIALLY_RECOVERED"
    assert data["verified_bytes"] == 84
    assert data["reconstructed_bytes"] == 0
    assert data["missing_bytes"] == 209


# ── Case F: Physically Fragmented CSV (Sparse Evidence) ────────────────────

def test_case_f_physically_fragmented_csv():
    """Case F: Physically fragmented CSV must detect the physical null gap as MISSING damage.

    Fragment 1: 27 bytes
    Missing physical gap: 57 bytes (null bytes)
    Fragment 2: 27 bytes
    Total: 111 bytes
    """
    frag1 = b"id,name,role\n1,alice,admin\n"
    frag2 = b"2,bob,user\n3,carol,analyst\n"
    gap = b"\x00" * 57
    content = frag1 + gap + frag2
    total_len = len(content)
    assert total_len == 111

    run = execute_traced_recovery("data.csv", content, detection_mode="known_file")
    assert run.status == "PARTIALLY_RECOVERED"
    assert run.status != "FULLY_RECOVERED"
    assert run.total_input_bytes == 111
    assert run.total_verified_bytes == 54
    assert run.total_reconstructed_bytes == 0
    assert run.total_missing_bytes == 57
    assert run.total_verified_bytes + run.total_reconstructed_bytes + run.total_missing_bytes == 111

    # Damage region must document the physical missing gap
    assert len(run.damage_regions) == 1
    damage = run.damage_regions[0]
    assert damage.type == "MISSING"
    assert damage.start_offset == 27
    assert damage.length == 57
    assert damage.end_offset == 84

    # 2 distinct fragments must be tracked
    assert len(run.fragments) == 2
    assert run.fragments[0].offset == 0
    assert run.fragments[0].length == 27
    assert run.fragments[1].offset == 84
    assert run.fragments[1].length == 27

    # API verification
    resp = client.post(
        "/api/recover-file",
        files={"file": ("data.csv", content, "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "PARTIALLY_RECOVERED"
    assert data["verified_bytes"] == 54
    assert data["reconstructed_bytes"] == 0
    assert data["missing_bytes"] == 57


# ── Case G: Deterministically Reconstructable Artifact (R > 0) ──────────────

def test_case_g_deterministic_reconstruction_accounting():
    """Case G: Deterministically repaired artifact with R > 0 must NOT be FULLY_RECOVERED."""
    # JSON missing closing brace
    content = b'{"name": "Alice", "role": "admin"'
    run = execute_traced_recovery("data.json", content, detection_mode="known_file")

    assert run.total_reconstructed_bytes > 0
    assert run.total_verified_bytes > 0
    # Because R > 0, it cannot be FULLY_RECOVERED
    assert run.status != "FULLY_RECOVERED"
    assert run.status == "PARTIALLY_RECOVERED"
    assert len(run.reconstruction_steps) >= 1
    assert run.total_verified_bytes + run.total_reconstructed_bytes + run.total_missing_bytes == len(content) + run.total_reconstructed_bytes


# ── Case H: Ambiguous Bifragment Reconstruction ─────────────────────────────

def test_case_h_ambiguous_bifragment_preserves_unresolved_gap():
    """Case H: Ambiguous bifragment search must preserve ambiguity without arbitrary picking."""
    frag_a = b"First line of log\nSecond line of log\n"
    frag_b = b"Third line of log\nFourth line of log\n"

    # In raw bifragment reconstruction with preserve_ambiguity=True:
    raw_res = reconstruct_bifragment(frag_a, frag_b, validator=validate_txt, min_gap=5, max_gap=50, preserve_ambiguity=True)
    assert raw_res.success is True
    assert raw_res.gap_size is None  # Ambiguity preserved
    assert raw_res.valid_candidate_count > 1
    assert raw_res.missing_region_metadata["status"] == "AMBIGUOUS_GAP"
    assert raw_res.missing_region_metadata["selected_gap_size"] is None

    # In reconstruct_fragment_pair with observed_gap:
    pair_res = reconstruct_fragment_pair("txt", frag_a, frag_b, observed_gap=50, min_gap=5, max_gap=50)
    assert pair_res.status == "PARTIALLY_RECOVERED"
    assert pair_res.details["search_discriminating"] is False
    assert pair_res.details["selected_gap_size"] is None
    assert pair_res.details["gap_size_determined"] is False
    assert pair_res.missing_bytes == 50
    assert pair_res.verified_bytes == len(frag_a) + len(frag_b)
    assert pair_res.reconstructed_bytes == 0
    assert pair_res.verified_bytes + pair_res.reconstructed_bytes + pair_res.missing_bytes == len(frag_a) + len(frag_b) + 50


# ── Case I: Unrecoverable Binary Noise / Garbage ─────────────────────────────

def test_case_i_unrecoverable_binary_noise():
    """Case I: Random corrupt bytes must be marked UNRECOVERABLE with V=0, R=0, M=len."""
    content = b"\x00\x99\xff\xfe\xdc\xba\x88\x77\x66\x55\x44" * 10
    total_len = len(content)

    run = execute_traced_recovery("garbage.bin", content)
    assert run.status == "UNRECOVERABLE"
    assert run.total_verified_bytes == 0
    assert run.total_reconstructed_bytes == 0
    assert run.total_missing_bytes == total_len
    assert len(run.reconstruction_steps) == 0

    # API test
    resp = client.post(
        "/api/recover-file",
        files={"file": ("corrupt.raw", content, "application/octet-stream")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "UNRECOVERABLE"
    assert data["verified_bytes"] == 0
    assert data["reconstructed_bytes"] == 0
    assert data["missing_bytes"] == total_len
    assert data["confidence_score"] == 0.0
    assert data["is_downloadable"] is False


# ── Blind Mode Completeness Invariant ───────────────────────────────────────

def test_blind_mode_never_claims_full_recovery_for_unstructured_text():
    """In blind carving from disk/streams, text and csv cannot establish full artifact completeness."""
    txt_content = b"Single line of carved text without bounds\n"
    txt_run = execute_traced_recovery("carved_blob.raw", txt_content, detection_mode="blind")
    assert txt_run.status == "PARTIALLY_RECOVERED"
    assert txt_run.status != "FULLY_RECOVERED"

    csv_content = b"col1,col2\nval1,val2\n"
    csv_run = execute_traced_recovery("carved_stream.raw", csv_content, detection_mode="blind")
    assert csv_run.status == "PARTIALLY_RECOVERED"
    assert csv_run.status != "FULLY_RECOVERED"
