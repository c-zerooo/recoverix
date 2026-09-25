"""
test_bifragment.py — Tests for Recoverix bounded bifragment reconstruction.

Covers: valid reconstruction, gap of 1, gap of 4096, out-of-range bounds rejection,
smallest-valid-gap selection when multiple candidates exist, safe failure on no valid gap,
fragment ordering validation, empty fragments, input type validation, immutability,
determinism, validator exception resilience, bound enforcement, pipeline integration
with seed-42 synthetic evidence, and verification that missing bytes are strictly metadata.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure imports work from the project root.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.app.models.reconstruction import BifragmentReconstructionResult
from backend.app.models.validation import ValidationResult
from backend.app.recovery.scanner import scan_evidence
from backend.app.recovery.carver import carve_candidate
from backend.app.recovery.validators import validate_txt, validate_csv
from backend.app.recovery.bifragment import reconstruct_bifragment


# ── Helpers ─────────────────────────────────────────────────────────

def _split_txt_artifact(body_lines: list[str], split_index: int = 48) -> tuple[bytes, bytes]:
    lines = [
        "[SYNTHETIC_ARTIFACT_START]",
        "filename: bifrag.txt",
        *body_lines,
        "[SYNTHETIC_ARTIFACT_END]",
    ]
    full = "\n".join(lines).encode("utf-8")
    return full[:split_index], full[split_index:]


# ── Tests ────────────────────────────────────────────────────────────

def test_valid_bifragment_reconstruction():
    frag_a, frag_b = _split_txt_artifact(["line1: data", "line2: more data"], split_index=30)
    result = reconstruct_bifragment(frag_a, frag_b, validator=validate_txt, min_gap=1, max_gap=100)

    assert isinstance(result, BifragmentReconstructionResult)
    assert result.success is True
    assert result.gap_size is not None
    assert result.gap_size >= 1
    assert result.missing_byte_count == result.gap_size
    assert result.valid_candidate_count >= 1
    assert isinstance(result.validation_result, ValidationResult)
    assert result.validation_result.valid is True
    # Verify metadata notes unknown/missing bytes without false recovery
    assert "unknown_bytes_notice" in result.missing_region_metadata


def test_gap_of_one_byte():
    # Construct fragments such that a gap of exactly 1 byte validates successfully.
    frag_a = b"[SYNTHETIC_ARTIFACT_START]\n"
    frag_b = b"end\n[SYNTHETIC_ARTIFACT_END]"
    # With min_gap=1, max_gap=1, gap size 1: frag_a + b"\n" + frag_b
    result = reconstruct_bifragment(frag_a, frag_b, validator=validate_txt, min_gap=1, max_gap=1)

    assert result.success is True
    assert result.gap_size == 1
    assert result.missing_byte_count == 1


def test_gap_of_max_bytes():
    frag_a = b"[SYNTHETIC_ARTIFACT_START]\n"
    frag_b = b"end\n[SYNTHETIC_ARTIFACT_END]"
    # Test with max_gap=4096
    result = reconstruct_bifragment(frag_a, frag_b, validator=validate_txt, min_gap=4096, max_gap=4096)

    assert result.success is True
    assert result.gap_size == 4096
    assert result.missing_byte_count == 4096


def test_gap_bounds_rejection():
    frag_a, frag_b = _split_txt_artifact(["test"])

    # min_gap < 1
    with pytest.raises(ValueError, match="min_gap must be >= 1"):
        reconstruct_bifragment(frag_a, frag_b, validator=validate_txt, min_gap=0, max_gap=100)

    # max_gap > 4096
    with pytest.raises(ValueError, match="max_gap must be <= 4096"):
        reconstruct_bifragment(frag_a, frag_b, validator=validate_txt, min_gap=1, max_gap=5000)

    # min_gap > max_gap
    with pytest.raises(ValueError, match="cannot be greater than max_gap"):
        reconstruct_bifragment(frag_a, frag_b, validator=validate_txt, min_gap=10, max_gap=5)


def test_smallest_valid_gap_selection():
    frag_a, frag_b = _split_txt_artifact(["data"])
    # If multiple gap sizes (e.g. 5, 10, 20) are valid, smallest (5) must be selected.
    result = reconstruct_bifragment(frag_a, frag_b, validator=validate_txt, min_gap=5, max_gap=50)

    assert result.success is True
    assert result.gap_size == 5
    assert result.valid_candidate_count > 1


def test_no_valid_gap_fails_safely():
    # Fragments with invalid UTF-8 bytes that cannot form a valid TXT artifact together
    frag_a = b"\xff\xfe\xfd"
    frag_b = b"\xfc\xfb\xfa"
    result = reconstruct_bifragment(frag_a, frag_b, validator=validate_txt, min_gap=1, max_gap=10)

    assert result.success is False
    assert result.gap_size is None
    assert result.missing_byte_count == 0
    assert result.validation_result is None
    assert result.valid_candidate_count == 0
    assert result.fragment_a_bytes == frag_a
    assert result.fragment_b_bytes == frag_b


def test_fragment_ordering_validation():
    # Reversed markers: frag_a has end marker, frag_b has start marker
    frag_a = b"[SYNTHETIC_ARTIFACT_END]"
    frag_b = b"[SYNTHETIC_ARTIFACT_START]"

    with pytest.raises(ValueError, match="Invalid fragment ordering"):
        reconstruct_bifragment(frag_a, frag_b, validator=validate_txt, min_gap=1, max_gap=10)


def test_empty_fragment_rejection():
    frag_ok, _ = _split_txt_artifact(["data"])

    with pytest.raises(ValueError, match="cannot be empty"):
        reconstruct_bifragment(b"", frag_ok, validator=validate_txt)

    with pytest.raises(ValueError, match="cannot be empty"):
        reconstruct_bifragment(frag_ok, b"", validator=validate_txt)


def test_invalid_fragment_inputs():
    frag_ok, _ = _split_txt_artifact(["data"])

    with pytest.raises(TypeError, match="Invalid type for fragment_a"):
        reconstruct_bifragment(12345, frag_ok, validator=validate_txt)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="Invalid type for fragment_b"):
        reconstruct_bifragment(frag_ok, None, validator=validate_txt)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="validator must be a callable"):
        reconstruct_bifragment(frag_ok, frag_ok, validator="not_a_callable")  # type: ignore[arg-type]


def test_input_immutability():
    artifact_a = bytearray(_split_txt_artifact(["data"])[0])
    artifact_b = bytearray(_split_txt_artifact(["data"])[1])
    orig_a = bytes(artifact_a)
    orig_b = bytes(artifact_b)

    reconstruct_bifragment(bytes(artifact_a), bytes(artifact_b), validator=validate_txt, min_gap=1, max_gap=10)

    assert bytes(artifact_a) == orig_a
    assert bytes(artifact_b) == orig_b


def test_determinism():
    frag_a, frag_b = _split_txt_artifact(["determinism test"])
    r1 = reconstruct_bifragment(frag_a, frag_b, validator=validate_txt, min_gap=1, max_gap=50)
    r2 = reconstruct_bifragment(frag_a, frag_b, validator=validate_txt, min_gap=1, max_gap=50)

    assert r1 == r2


def test_validator_exception_resilience():
    frag_a, frag_b = _split_txt_artifact(["test"])

    def faulty_validator(data: bytes) -> ValidationResult:
        if len(data) < 100:
            raise RuntimeError("Parser failure on small data")
        return validate_txt(data)

    # Should not crash, and should find valid gap when total length >= threshold (100)
    result = reconstruct_bifragment(frag_a, frag_b, validator=faulty_validator, min_gap=1, max_gap=200)
    assert result.success is True
    assert result.gap_size is not None
    assert len(frag_a) + result.gap_size + len(frag_b) >= 100


def test_max_bound_enforcement():
    frag_a, frag_b = _split_txt_artifact(["test"])
    # Ensure range cannot exceed 4096
    with pytest.raises(ValueError, match="max_gap must be <= 4096"):
        reconstruct_bifragment(frag_a, frag_b, validator=validate_txt, min_gap=1, max_gap=5000)


def test_pipeline_integration_seed_42(tmp_path):
    """Full pipeline: Evidence -> Scanner -> Candidate -> Carver -> Validator -> Bifragment Reconstruction"""
    from backend.generate_case import generate_evidence

    generate_evidence(42, tmp_path)
    img = (tmp_path / "damaged.img").read_bytes()

    candidates = scan_evidence(img)
    carveable = [c for c in candidates if c.estimated_end_offset is not None]
    assert len(carveable) >= 1

    # Take first carveable artifact, split into 2 fragments to test bifragment reconstruction
    cand = carveable[0]
    artifact = carve_candidate(img, cand)
    raw = artifact.recovered_bytes

    if len(raw) > 20:
        mid = len(raw) // 2
        frag_a = raw[:mid]
        frag_b = raw[mid:]

        validator = validate_txt if artifact.format == "txt" else validate_csv
        recon = reconstruct_bifragment(frag_a, frag_b, validator=validator, min_gap=1, max_gap=500)
        assert isinstance(recon, BifragmentReconstructionResult)


def test_missing_bytes_are_metadata_only():
    frag_a, frag_b = _split_txt_artifact(["metadata check"])
    result = reconstruct_bifragment(frag_a, frag_b, validator=validate_txt, min_gap=1, max_gap=50)

    assert result.success is True
    # Ensure missing bytes are NOT included in fragment_a_bytes or fragment_b_bytes
    assert result.gap_size is not None
    assert result.missing_byte_count == result.gap_size
    assert "unknown_bytes_notice" in result.missing_region_metadata
    # Ensure known bytes remain untouched
    assert result.fragment_a_bytes == frag_a
    assert result.fragment_b_bytes == frag_b
