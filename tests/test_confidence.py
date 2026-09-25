"""
test_confidence.py — Tests for Recoverix confidence engine and lightweight provenance.

Covers all 20 required test scenarios:
1. Perfect contiguous valid artifact (score=100, FULLY_RECOVERED, zero reconstructed/missing bytes)
2. Valid artifact with missing/reconstructed region (score>=85 downgraded to PARTIALLY_RECOVERED)
3. Missing header (header_validity = 0)
4. Missing footer (footer_validity = 0)
5. Structural validation failure (structural_validation = 0)
6. Invalid artifact (low score / appropriate status)
7. Exact threshold boundaries (85, 84, 50, 49, 20, 19, 0)
8. Reconstruction integrity points (15 on success, 0 on failure)
9. No reconstruction required (full 15 points)
10. Provenance byte accounting consistency
11. Task 6 placeholder bytes excluded from verified evidence
12. Input immutability
13. Determinism
14. Component maximums (20, 20, 30, 15, 15)
15. Total maximum score cap (100)
16. Score minimum bound (0)
17. Deterministic status classification
18. Absence of AI_PREDICTED_INFILL terminology
19. End-to-end pipeline integration
20. Seed-42 synthetic evidence integration
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure imports work from the project root.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.app.models.confidence import (
    RecoveryStatus,
    ConfidenceBreakdown,
    ArtifactProvenance,
    ConfidenceEvaluationResult,
)
from backend.app.models.validation import ValidationResult
from backend.app.models.reconstruction import BifragmentReconstructionResult
from backend.app.recovery.scanner import scan_evidence
from backend.app.recovery.carver import carve_candidate, RecoveredArtifact
from backend.app.recovery.validators import validate_txt, validate_csv
from backend.app.recovery.bifragment import reconstruct_bifragment
from backend.app.scoring.confidence import (
    calculate_confidence,
    classify_recovery_status,
    build_provenance,
    evaluate_artifact_confidence,
)


# ── Helpers ─────────────────────────────────────────────────────────

def _make_txt_payload(body: str = "line1: hello\nline2: world") -> bytes:
    lines = [
        "[SYNTHETIC_ARTIFACT_START]",
        "filename: test.txt",
        body,
        "[SYNTHETIC_ARTIFACT_END]",
    ]
    return "\n".join(lines).encode("utf-8")


# ── 1. Perfect Contiguous Valid Artifact ───────────────────────────

def test_perfect_contiguous_valid_artifact():
    payload = _make_txt_payload()
    val_res = validate_txt(payload)

    res = evaluate_artifact_confidence(validation_result=val_res, artifact=payload)

    assert res.score_breakdown.total == 100
    assert res.score_breakdown.header_validity == 20
    assert res.score_breakdown.footer_validity == 20
    assert res.score_breakdown.structural_validation == 30
    assert res.score_breakdown.size_plausibility == 15
    assert res.score_breakdown.reconstruction_integrity == 15

    assert res.status == RecoveryStatus.FULLY_RECOVERED
    assert res.provenance.verified_bytes == len(payload)
    assert res.provenance.reconstructed_bytes == 0
    assert res.provenance.missing_bytes == 0
    assert res.provenance.reconstruction_method == "NONE"
    assert res.provenance.validation_status == "PASSED"


# ── 2. Reconstructed Bytes Overrides Fully Recovered Status ──────

def test_reconstructed_bytes_overrides_fully_recovered_status():
    frag_a = b"[SYNTHETIC_ARTIFACT_START]\nfilename: test.txt\n"
    frag_b = b"body_data\n[SYNTHETIC_ARTIFACT_END]"

    recon_res = reconstruct_bifragment(frag_a, frag_b, validator=validate_txt, min_gap=1, max_gap=10)
    assert recon_res.success is True
    assert recon_res.validation_result is not None

    # Status classification with reconstructed_bytes > 0 and score >= 85 (100) -> PARTIALLY_RECOVERED
    status = classify_recovery_status(score=100, reconstructed_bytes=5, missing_bytes=0)
    assert status == RecoveryStatus.PARTIALLY_RECOVERED
    assert status != RecoveryStatus.FULLY_RECOVERED


# ── 3. Missing Header ───────────────────────────────────────────────

def test_missing_header_score():
    # Payload missing start marker
    payload = b"filename: test.txt\ndata\n[SYNTHETIC_ARTIFACT_END]"
    val_res = validate_txt(payload)

    breakdown = calculate_confidence(val_res, artifact=payload)

    assert breakdown.header_validity == 0
    assert breakdown.total < 100


# ── 4. Missing Footer ───────────────────────────────────────────────

def test_missing_footer_score():
    # Payload missing end marker
    payload = b"[SYNTHETIC_ARTIFACT_START]\nfilename: test.txt\ndata"
    val_res = validate_txt(payload)

    breakdown = calculate_confidence(val_res, artifact=payload)

    assert breakdown.footer_validity == 0
    assert breakdown.total < 100


# ── 5. Structural Validation Failure ────────────────────────────────

def test_structural_validation_failure_score():
    val_res = ValidationResult(
        valid=False,
        format="txt",
        checks_performed=["utf8_decoding"],
        errors=["UTF-8 decoding failed"],
    )

    breakdown = calculate_confidence(val_res)

    assert breakdown.structural_validation == 0


# ── 6. Invalid Artifact Scoring and Classification ──────────────────

def test_invalid_artifact_scoring_and_status():
    val_res = ValidationResult(
        valid=False,
        format="txt",
        checks_performed=["input_type"],
        errors=["Missing synthetic start marker", "Missing synthetic end marker"],
    )

    res = evaluate_artifact_confidence(validation_result=val_res)

    assert res.score_breakdown.header_validity == 0
    assert res.score_breakdown.footer_validity == 0
    assert res.score_breakdown.structural_validation == 0
    assert res.score_breakdown.total == 0
    assert res.status == RecoveryStatus.UNRECOVERABLE


# ── 7. Exact Threshold Boundary Tests ───────────────────────────────

def test_exact_status_threshold_boundaries():
    # 85 without reconstructed bytes -> FULLY_RECOVERED
    assert classify_recovery_status(85, reconstructed_bytes=0, missing_bytes=0) == RecoveryStatus.FULLY_RECOVERED
    # 85 WITH missing_bytes (reconstructed_bytes=0) -> FULLY_RECOVERED (missing_bytes alone does NOT downgrade lower/other statuses)
    assert classify_recovery_status(85, reconstructed_bytes=0, missing_bytes=10) == RecoveryStatus.FULLY_RECOVERED
    # 85 WITH reconstructed_bytes -> PARTIALLY_RECOVERED (Override)
    assert classify_recovery_status(85, reconstructed_bytes=5, missing_bytes=0) == RecoveryStatus.PARTIALLY_RECOVERED

    # Explicitly requested threshold & override test cases:
    # 1. score 92 reconstructed_bytes=100 -> PARTIALLY_RECOVERED
    assert classify_recovery_status(92, reconstructed_bytes=100, missing_bytes=0) == RecoveryStatus.PARTIALLY_RECOVERED
    # 2. score 84 reconstructed_bytes=100 -> PARTIALLY_RECOVERED
    assert classify_recovery_status(84, reconstructed_bytes=100, missing_bytes=0) == RecoveryStatus.PARTIALLY_RECOVERED
    # 3. score 49 missing_bytes=100 reconstructed_bytes=0 -> CORRUPTED
    assert classify_recovery_status(49, reconstructed_bytes=0, missing_bytes=100) == RecoveryStatus.CORRUPTED
    # 4. score 19 missing_bytes=100 reconstructed_bytes=0 -> UNRECOVERABLE
    assert classify_recovery_status(19, reconstructed_bytes=0, missing_bytes=100) == RecoveryStatus.UNRECOVERABLE
    # 5. score 0 missing_bytes=100 reconstructed_bytes=0 -> UNRECOVERABLE
    assert classify_recovery_status(0, reconstructed_bytes=0, missing_bytes=100) == RecoveryStatus.UNRECOVERABLE

    # 84 -> PARTIALLY_RECOVERED
    assert classify_recovery_status(84, reconstructed_bytes=0, missing_bytes=0) == RecoveryStatus.PARTIALLY_RECOVERED

    # 50 -> PARTIALLY_RECOVERED
    assert classify_recovery_status(50, reconstructed_bytes=0, missing_bytes=0) == RecoveryStatus.PARTIALLY_RECOVERED

    # 49 -> CORRUPTED
    assert classify_recovery_status(49, reconstructed_bytes=0, missing_bytes=0) == RecoveryStatus.CORRUPTED

    # 20 -> CORRUPTED
    assert classify_recovery_status(20, reconstructed_bytes=0, missing_bytes=0) == RecoveryStatus.CORRUPTED

    # 19 -> UNRECOVERABLE
    assert classify_recovery_status(19, reconstructed_bytes=0, missing_bytes=0) == RecoveryStatus.UNRECOVERABLE

    # 0 -> UNRECOVERABLE
    assert classify_recovery_status(0, reconstructed_bytes=0, missing_bytes=0) == RecoveryStatus.UNRECOVERABLE


# ── 8. Reconstruction Integrity Points ──────────────────────────────

def test_reconstruction_integrity_scoring():
    frag_a = b"[SYNTHETIC_ARTIFACT_START]\nfilename: test.txt\n"
    frag_b = b"body_data\n[SYNTHETIC_ARTIFACT_END]"

    # Successful bifragment reconstruction -> 15 points
    recon_ok = reconstruct_bifragment(frag_a, frag_b, validator=validate_txt, min_gap=1, max_gap=10)
    b_ok = calculate_confidence(recon_ok.validation_result, reconstruction_result=recon_ok)
    assert b_ok.reconstruction_integrity == 15

    # Failed bifragment reconstruction -> 0 points
    recon_fail = reconstruct_bifragment(b"bad_a", b"bad_b", validator=validate_txt, min_gap=1, max_gap=5)
    val_fail = ValidationResult(valid=False, format="txt")
    b_fail = calculate_confidence(val_fail, reconstruction_result=recon_fail)
    assert b_fail.reconstruction_integrity == 0


# ── 9. No Reconstruction Required ───────────────────────────────────

def test_no_reconstruction_integrity_scoring():
    payload = _make_txt_payload()
    val_res = validate_txt(payload)

    # When reconstruction_result is None, full 15 points awarded
    breakdown = calculate_confidence(val_res, reconstruction_result=None, artifact=payload)
    assert breakdown.reconstruction_integrity == 15


# ── 10. Provenance Byte Accounting Consistency ──────────────────────

def test_provenance_byte_accounting():
    frag_a = b"12345"
    frag_b = b"67890"

    val_res = validate_txt(_make_txt_payload())
    recon_res = BifragmentReconstructionResult(
        success=True,
        format="txt",
        fragment_a_id="fa",
        fragment_b_id="fb",
        gap_size=12,
        missing_byte_count=12,
        reconstruction_method="BIFRAGMENT_GAP",
        validation_result=val_res,
        fragment_a_bytes=frag_a,
        fragment_b_bytes=frag_b,
    )

    prov = build_provenance(val_res, reconstruction_result=recon_res)

    assert prov.verified_bytes == 10  # len(frag_a) + len(frag_b)
    assert prov.reconstructed_bytes == 0
    assert prov.missing_bytes == 12
    assert prov.reconstruction_method == "BIFRAGMENT_GAP"


# ── 11. Task 6 Placeholder Bytes Excluded from Verified Evidence ─────

def test_placeholder_bytes_not_counted_as_verified():
    frag_a = b"[SYNTHETIC_ARTIFACT_START]\nfilename: test.txt\n"
    frag_b = b"data\n[SYNTHETIC_ARTIFACT_END]"

    recon_res = reconstruct_bifragment(frag_a, frag_b, validator=validate_txt, min_gap=5, max_gap=10)
    prov = build_provenance(recon_res.validation_result, reconstruction_result=recon_res)

    # verified_bytes must equal len(frag_a) + len(frag_b), excluding the gap bytes
    expected_known_bytes = len(frag_a) + len(frag_b)
    assert prov.verified_bytes == expected_known_bytes
    assert prov.verified_bytes != (expected_known_bytes + recon_res.gap_size)


# ── 12. Input Immutability ──────────────────────────────────────────

def test_input_immutability():
    payload = bytearray(_make_txt_payload())
    orig_payload = bytes(payload)
    val_res = validate_txt(bytes(payload))

    calculate_confidence(val_res, artifact=bytes(payload))
    build_provenance(val_res, artifact=bytes(payload))
    evaluate_artifact_confidence(val_res, artifact=bytes(payload))

    assert bytes(payload) == orig_payload


# ── 13. Determinism ─────────────────────────────────────────────────

def test_scoring_determinism():
    payload = _make_txt_payload()
    val_res = validate_txt(payload)

    r1 = evaluate_artifact_confidence(val_res, artifact=payload)
    r2 = evaluate_artifact_confidence(val_res, artifact=payload)

    assert r1 == r2


# ── 14. Component Maximums ───────────────────────────────────────────

def test_component_maximums_enforced():
    payload = _make_txt_payload()
    val_res = validate_txt(payload)
    b = calculate_confidence(val_res, artifact=payload)

    assert b.header_validity <= 20
    assert b.footer_validity <= 20
    assert b.structural_validation <= 30
    assert b.size_plausibility <= 15
    assert b.reconstruction_integrity <= 15


# ── 15. Total Maximum Bound ─────────────────────────────────────────

def test_total_maximum_score_bound():
    payload = _make_txt_payload()
    val_res = validate_txt(payload)
    b = calculate_confidence(val_res, artifact=payload)

    assert b.total <= 100


# ── 16. Score Minimum Bound ─────────────────────────────────────────

def test_score_minimum_bound():
    val_res = ValidationResult(valid=False, format="txt", errors=["start marker", "end marker"])
    b = calculate_confidence(val_res)

    assert b.total >= 0


# ── 17. Deterministic Status Classification ─────────────────────────

def test_status_classification_defensive_bounds():
    with pytest.raises(ValueError, match="Score must be between 0 and 100"):
        classify_recovery_status(-1)

    with pytest.raises(ValueError, match="Score must be between 0 and 100"):
        classify_recovery_status(101)


# ── 18. Absence of AI_PREDICTED_INFILL Terminology ──────────────────

def test_forbidden_ai_infill_terminology_rejected():
    with pytest.raises(ValueError, match="Forbidden terminology"):
        ArtifactProvenance(
            verified_bytes=100,
            reconstructed_bytes=10,
            missing_bytes=0,
            reconstruction_method="AI_PREDICTED_INFILL",
            validation_status="PASSED",
        )


# ── 19. Full Pipeline Integration Test ───────────────────────────────

def test_full_pipeline_integration(tmp_path):
    """Full pipeline: Evidence -> Scanner -> Carver -> Validator -> Bifragment Reconstruction -> Confidence Engine -> Provenance"""
    from backend.generate_case import generate_evidence

    generate_evidence(42, tmp_path)
    img = (tmp_path / "damaged.img").read_bytes()

    # 1. Scanner
    candidates = scan_evidence(img)
    carveable = [c for c in candidates if c.estimated_end_offset is not None]
    assert len(carveable) >= 1

    # 2. Carver
    artifact: RecoveredArtifact = carve_candidate(img, carveable[0])

    # 3. Validator
    val_res = validate_txt(artifact) if artifact.format == "txt" else validate_csv(artifact)

    # 4. Confidence & Provenance
    eval_res = evaluate_artifact_confidence(validation_result=val_res, artifact=artifact)

    assert isinstance(eval_res, ConfidenceEvaluationResult)
    assert isinstance(eval_res.score_breakdown, ConfidenceBreakdown)
    assert isinstance(eval_res.status, RecoveryStatus)
    assert isinstance(eval_res.provenance, ArtifactProvenance)
    assert eval_res.score_breakdown.total >= 0
    assert eval_res.provenance.verified_bytes == artifact.recovered_byte_count
    assert eval_res.provenance.validation_status in ("PASSED", "FAILED")


# ── 20. Seed-42 Synthetic Evidence Integration ───────────────────────

def test_seed_42_synthetic_bifragment_confidence(tmp_path):
    from backend.generate_case import generate_evidence

    generate_evidence(42, tmp_path)
    img = (tmp_path / "damaged.img").read_bytes()

    candidates = scan_evidence(img)
    carveable = [c for c in candidates if c.estimated_end_offset is not None]
    artifact = carve_candidate(img, carveable[0])
    raw = artifact.recovered_bytes

    if len(raw) > 20:
        mid = len(raw) // 2
        frag_a = raw[:mid]
        frag_b = raw[mid:]

        validator = validate_txt if artifact.format == "txt" else validate_csv
        recon = reconstruct_bifragment(frag_a, frag_b, validator=validator, min_gap=1, max_gap=500)

        eval_res = evaluate_artifact_confidence(
            validation_result=recon.validation_result,
            reconstruction_result=recon,
        )

        assert eval_res.provenance.missing_bytes == recon.gap_size
        assert eval_res.provenance.reconstruction_method == "BIFRAGMENT_GAP"
        assert eval_res.provenance.validation_status == "PASSED"
