"""
test_validators.py — Tests for Recoverix structural validators (TXT, CSV).

Covers: valid TXT/CSV, missing start/end markers, reversed markers, empty input,
invalid UTF-8, truncated artifacts, malformed CSV, inconsistent row structure,
input immutability, determinism, public API re-exports, and full pipeline integration.
"""

from __future__ import annotations

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
from backend.app.recovery.validators import validate_txt, validate_csv


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


# ── 3. General & Pipeline Integration Tests ─────────────────────────

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
