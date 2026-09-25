"""
test_validators.py — Tests for Recoverix structural validators (TXT, CSV, JSON, XML, PNG, JPEG).

Covers: valid TXT/CSV/JSON/XML/PNG/JPEG, missing start/end markers, reversed markers, empty input,
invalid UTF-8, truncated artifacts, malformed structures, inconsistent row structure,
input immutability, determinism, public API re-exports, format registry, and full pipeline integration.
"""

from __future__ import annotations

import struct
import zlib
import sys
from pathlib import Path

import pytest

# Ensure imports work from the project root.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.app.models.validation import ValidationResult
from backend.app.recovery.scanner import scan_evidence
from backend.app.recovery.carver import carve_candidate, RecoveredArtifact
from backend.app.recovery.validators import (
    validate_txt,
    validate_csv,
    validate_json,
    validate_xml,
    validate_png,
    validate_jpeg,
    validate_artifact,
)
from backend.app.recovery.registry import get_format_spec, list_supported_formats


# ── Helpers ─────────────────────────────────────────────────────────

def _make_txt_artifact(body_lines: list[str]) -> bytes:
    lines = [
        "[SYNTHETIC_ARTIFACT_START]",
        "filename: test.txt",
        *body_lines,
        "[SYNTHETIC_ARTIFACT_END]",
    ]
    return "\n".join(lines).encode("utf-8")


def _make_csv_artifact(rows: list[list[str]]) -> bytes:
    lines = ["[SYNTHETIC_ARTIFACT_START]"]
    for row in rows:
        lines.append(",".join(row))
    lines.append("[SYNTHETIC_ARTIFACT_END]")
    return "\n".join(lines).encode("utf-8")


def _make_png_bytes(width: int = 16, height: int = 16) -> bytes:
    """Construct minimal structurally valid PNG binary data with correct CRC32 checksums."""
    png_magic = b"\x89PNG\r\n\x1a\n"

    # IHDR Chunk
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 13 bytes
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF
    ihdr_chunk = struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)

    # IDAT Chunk (dummy compressed data)
    dummy_data = zlib.compress(b"\x00" * (width * height * 3))
    idat_crc = zlib.crc32(b"IDAT" + dummy_data) & 0xFFFFFFFF
    idat_chunk = struct.pack(">I", len(dummy_data)) + b"IDAT" + dummy_data + struct.pack(">I", idat_crc)

    # IEND Chunk
    iend_crc = zlib.crc32(b"IEND") & 0xFFFFFFFF
    iend_chunk = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)

    return png_magic + ihdr_chunk + idat_chunk + iend_chunk


def _make_jpeg_bytes(width: int = 16, height: int = 16) -> bytes:
    """Construct minimal structurally valid JPEG binary data stream."""
    soi = b"\xff\xd8"
    eoi = b"\xff\xd9"

    # SOF0 Marker (Start of Frame 0 - Baseline DCT)
    sof0_payload = struct.pack(">BHHB", 8, height, width, 3) + b"\x01\x11\x00\x02\x11\x01\x03\x11\x01"
    sof0_len = len(sof0_payload) + 2
    sof0 = b"\xff\xc0" + struct.pack(">H", sof0_len) + sof0_payload

    # SOS Marker (Start of Scan)
    sos_payload = b"\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00"
    sos_len = len(sos_payload) + 2
    sos = b"\xff\xda" + struct.pack(">H", sos_len) + sos_payload

    # Minimal scan data stream before EOI
    scan_data = b"\x00\x7f"

    return soi + sof0 + sos + scan_data + eoi


# ── 1. TXT Validator Tests ──────────────────────────────────────────

def test_valid_txt():
    artifact = _make_txt_artifact(["line1: hello", "line2: world"])
    result = validate_txt(artifact)

    assert isinstance(result, ValidationResult)
    assert result.valid is True
    assert result.format == "txt"
    assert len(result.errors) == 0
    assert "utf8_decoding" in result.checks_performed
    assert result.details.get("line_count") == 5


def test_txt_missing_start_marker():
    artifact = b"filename: test.txt\n[SYNTHETIC_ARTIFACT_END]"
    result = validate_txt(artifact)

    assert result.valid is False
    assert any("start marker" in e for e in result.errors)


def test_txt_missing_end_marker():
    artifact = b"[SYNTHETIC_ARTIFACT_START]\nfilename: test.txt"
    result = validate_txt(artifact)

    assert result.valid is False
    assert any("end marker" in e for e in result.errors)


def test_txt_reversed_markers():
    artifact = b"[SYNTHETIC_ARTIFACT_END]\ndata\n[SYNTHETIC_ARTIFACT_START]"
    result = validate_txt(artifact)

    assert result.valid is False
    assert any("Invalid marker ordering" in e for e in result.errors)


def test_txt_empty_input():
    result = validate_txt(b"")

    assert result.valid is False
    assert any("empty" in e for e in result.errors)


def test_txt_invalid_utf8():
    artifact = b"[SYNTHETIC_ARTIFACT_START]\n\xff\xfe invalid utf8\n[SYNTHETIC_ARTIFACT_END]"
    result = validate_txt(artifact)

    assert result.valid is False
    assert any("UTF-8 decoding failed" in e for e in result.errors)


def test_txt_truncated_artifact():
    artifact = b"[SYNTHETIC_ARTIFACT_START]\ntruncated content without end"
    result = validate_txt(artifact)

    assert result.valid is False
    assert len(result.errors) >= 1


def test_txt_determinism():
    artifact = _make_txt_artifact(["key: val"])
    r1 = validate_txt(artifact)
    r2 = validate_txt(artifact)

    assert r1 == r2
    assert r1.valid == r2.valid


# ── 2. CSV Validator Tests ──────────────────────────────────────────

def test_valid_csv():
    artifact = _make_csv_artifact([["col1", "col2"], ["val1", "val2"]])
    result = validate_csv(artifact)

    assert isinstance(result, ValidationResult)
    assert result.valid is True
    assert result.format == "csv"
    assert len(result.errors) == 0
    assert result.details.get("row_count") == 2
    assert result.details.get("column_counts") == [2, 2]


def test_csv_multiple_rows():
    rows = [["id", "name", "role"], ["1", "alice", "admin"], ["2", "bob", "user"]]
    artifact = _make_csv_artifact(rows)
    result = validate_csv(artifact)

    assert result.valid is True
    assert result.details.get("row_count") == 3
    assert result.details.get("column_counts") == [3, 3, 3]


def test_csv_consistent_columns():
    artifact = _make_csv_artifact([["a", "b", "c"], ["1", "2", "3"]])
    result = validate_csv(artifact)

    assert result.valid is True


def test_csv_missing_start_marker():
    artifact = b"col1,col2\nval1,val2\n[SYNTHETIC_ARTIFACT_END]"
    result = validate_csv(artifact)

    assert result.valid is False
    assert any("start marker" in e for e in result.errors)


def test_csv_missing_end_marker():
    artifact = b"[SYNTHETIC_ARTIFACT_START]\ncol1,col2\nval1,val2"
    result = validate_csv(artifact)

    assert result.valid is False
    assert any("end marker" in e for e in result.errors)


def test_csv_reversed_markers():
    artifact = b"[SYNTHETIC_ARTIFACT_END]\ncol1,col2\n[SYNTHETIC_ARTIFACT_START]"
    result = validate_csv(artifact)

    assert result.valid is False
    assert any("Invalid marker ordering" in e for e in result.errors)


def test_csv_empty_input():
    result = validate_csv(b"")

    assert result.valid is False
    assert any("empty" in e for e in result.errors)


def test_csv_invalid_utf8():
    artifact = b"[SYNTHETIC_ARTIFACT_START]\n\x80\x81,bad_utf8\n[SYNTHETIC_ARTIFACT_END]"
    result = validate_csv(artifact)

    assert result.valid is False
    assert any("UTF-8 decoding failed" in e for e in result.errors)


def test_csv_malformed_empty_body():
    artifact = b"[SYNTHETIC_ARTIFACT_START]\n\n[SYNTHETIC_ARTIFACT_END]"
    result = validate_csv(artifact)

    assert result.valid is False
    assert any("no data rows" in e for e in result.errors)


def test_csv_inconsistent_row_structure():
    artifact = _make_csv_artifact([["col1", "col2", "col3"], ["val1", "val2"]])
    result = validate_csv(artifact)

    assert result.valid is False
    assert any("Inconsistent row structure" in e for e in result.errors)


def test_csv_truncated_artifact():
    artifact = b"[SYNTHETIC_ARTIFACT_START]\ncol1,col2\nval1"
    result = validate_csv(artifact)

    assert result.valid is False


def test_csv_determinism():
    artifact = _make_csv_artifact([["x", "y"], ["1", "2"]])
    r1 = validate_csv(artifact)
    r2 = validate_csv(artifact)

    assert r1 == r2


# ── 3. JSON Validator Tests ─────────────────────────────────────────

def test_valid_json_direct():
    data = b'{"case_id": "c001", "recovered": true, "items": [1, 2, 3]}'
    res = validate_json(data)

    assert res.valid is True
    assert res.format == "json"
    assert res.details.get("root_type") == "dict"
    assert res.details.get("key_count") == 3


def test_valid_json_synthetic_markers():
    data = b'[SYNTHETIC_ARTIFACT_START]\n{"status": "ok", "code": 200}\n[SYNTHETIC_ARTIFACT_END]'
    res = validate_json(data)

    assert res.valid is True
    assert res.format == "json"
    assert res.details.get("key_count") == 2


def test_invalid_json_syntax():
    data = b'{"case_id": "c001", "unclosed": }'
    res = validate_json(data)

    assert res.valid is False
    assert any("JSON parsing failed" in e for e in res.errors)


# ── 4. XML Validator Tests ──────────────────────────────────────────

def test_valid_xml_direct():
    data = b'<?xml version="1.0"?><evidence id="e1"><artifact type="png">data</artifact></evidence>'
    res = validate_xml(data)

    assert res.valid is True
    assert res.format == "xml"
    assert res.details.get("root_tag") == "evidence"
    assert res.details.get("child_count") == 1
    assert res.details.get("attribute_count") == 1


def test_valid_xml_synthetic_markers():
    data = b'[SYNTHETIC_ARTIFACT_START]\n<root><item>1</item></root>\n[SYNTHETIC_ARTIFACT_END]'
    res = validate_xml(data)

    assert res.valid is True
    assert res.format == "xml"
    assert res.details.get("root_tag") == "root"


def test_invalid_xml_syntax():
    data = b'<?xml version="1.0"?><root><unclosed></root>'
    res = validate_xml(data)

    assert res.valid is False
    assert any("XML parsing failed" in e for e in res.errors)


# ── 5. PNG Validator Tests ──────────────────────────────────────────

def test_valid_png():
    png_data = _make_png_bytes(width=32, height=24)
    res = validate_png(png_data)

    assert res.valid is True
    assert res.format == "png"
    assert res.details.get("width") == 32
    assert res.details.get("height") == 24
    assert res.details.get("idat_count") >= 1


def test_invalid_png_magic():
    png_data = b"NOT_A_PNG_HEADER" + _make_png_bytes()[8:]
    res = validate_png(png_data)

    assert res.valid is False
    assert any("magic signature" in e for e in res.errors)


def test_corrupted_png_crc():
    png_data = bytearray(_make_png_bytes())
    # Corrupt a byte inside IHDR payload
    png_data[16] ^= 0xFF
    res = validate_png(bytes(png_data))

    assert res.valid is False
    assert any("CRC verification failed" in e for e in res.errors)


# ── 6. JPEG Validator Tests ─────────────────────────────────────────

def test_valid_jpeg():
    jpeg_data = _make_jpeg_bytes(width=64, height=48)
    res = validate_jpeg(jpeg_data)

    assert res.valid is True
    assert res.format == "jpeg"
    assert res.details.get("width") == 64
    assert res.details.get("height") == 48


def test_invalid_jpeg_soi():
    jpeg_data = b"\x00\x00" + _make_jpeg_bytes()[2:]
    res = validate_jpeg(jpeg_data)

    assert res.valid is False
    assert any("SOI" in e for e in res.errors)


def test_missing_jpeg_eoi():
    jpeg_data = _make_jpeg_bytes()[:-2]  # strip EOI marker
    res = validate_jpeg(jpeg_data)

    assert res.valid is False
    assert any("EOI" in e for e in res.errors)


# ── 7. Registry & Unified Validator Routing Tests ────────────────────

def test_format_registry_lookup():
    for fmt in list_supported_formats():
        spec = get_format_spec(fmt)
        assert spec is not None
        assert spec.format == fmt
        assert callable(spec.validator)


def test_unified_validate_artifact():
    json_bytes = b'{"valid": true}'
    res = validate_artifact("json", json_bytes)
    assert res.valid is True

    jpeg_bytes = _make_jpeg_bytes()
    res_jpg = validate_artifact("jpg", jpeg_bytes)
    assert res_jpg.valid is True

    res_unsupported = validate_artifact("invalid_fmt", b"data")
    assert res_unsupported.valid is False


# ── 8. General & Pipeline Integration Tests ─────────────────────────

def test_validators_do_not_mutate_input():
    artifact = bytearray(_make_txt_artifact(["mutate: test"]))
    original = bytes(artifact)

    validate_txt(bytes(artifact))
    validate_csv(bytes(artifact))

    assert bytes(artifact) == original


def test_invalid_input_type():
    r_txt = validate_txt(12345)  # type: ignore[arg-type]
    assert r_txt.valid is False
    assert any("Invalid input type" in e for e in r_txt.errors)

    r_csv = validate_csv(None)  # type: ignore[arg-type]
    assert r_csv.valid is False
    assert any("Invalid input type" in e for e in r_csv.errors)


def test_public_api_reexports():
    from backend.app import recovery

    assert hasattr(recovery, "ValidationResult")
    assert hasattr(recovery, "validate_txt")
    assert hasattr(recovery, "validate_csv")


def test_pipeline_integration_seed_42(tmp_path):
    """Full pipeline: Evidence -> Scanner -> Candidate -> Carver -> RecoveredArtifact -> Validator -> ValidationResult"""
    from backend.generate_case import generate_evidence

    generate_evidence(42, tmp_path)
    img = (tmp_path / "damaged.img").read_bytes()

    # 1. Scanner
    candidates = scan_evidence(img)
    assert len(candidates) >= 3

    carveable = [c for c in candidates if c.estimated_end_offset is not None]
    assert len(carveable) >= 1

    # 2. Carver & Validator pipeline
    validated_count = 0
    for cand in carveable:
        artifact: RecoveredArtifact = carve_candidate(img, cand)
        if artifact.format == "txt":
            v_res = validate_txt(artifact)
            assert isinstance(v_res, ValidationResult)
            validated_count += 1
        elif artifact.format == "csv":
            v_res = validate_csv(artifact)
            assert isinstance(v_res, ValidationResult)
            validated_count += 1

    assert validated_count >= 1
