"""
test_recovery_adapter.py — Comprehensive test suite for RecoveryRun -> ArtifactResponse adapter.

Validates:
  1. FULLY_RECOVERED: intact evidence, status preserved, confidence preserved, V/R/M preserved,
     size_bytes reflects actual recovered payload bytes.
  2. PARTIALLY_RECOVERED fragmented evidence: M > 0 preserved, V/R/M preserved exactly,
     missing bytes never become recovered bytes.
  3. Reconstructed JSON: R > 0 preserved, reconstruction method preserved, status remains PARTIALLY_RECOVERED.
  4. UNRECOVERABLE: status preserved, V/R/M preserved, size_bytes == 0, content_preview is None.
  5. Immutability test: original RecoveryRun is never mutated by the adapter.
  6. Honesty test: adapter never alters byte counts or recalculates status.
  7. Regression A (artifact_id): no fabricated UUID is generated when artifact_id is missing (raises ValueError).
  8. Regression B (confidence):
     - canonical integer confidence is preserved exactly without alteration.
     - documented float-to-integer representation conversion satisfies schema contract.
  9. Regression C (size_bytes):
     - when V + R > 0 exists but recovered_bytes are unavailable, adapter does NOT falsely claim
       V + R as payload size; size_bytes is strictly 0.
  10. Edge cases: missing/malformed recovered bytes and empty/incomplete confidence dictionaries.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import pytest

from backend.app.models.artifact import (
    ArtifactProvenanceSchema,
    ArtifactResponse,
    ConfidenceBreakdownSchema,
)
from backend.app.models.recovery_run import DamageRegion, Fragment, ReconstructionStep, RecoveryRun
from backend.app.recovery.adapter import (
    _compute_score_breakdown_schema,
    extract_recovered_bytes,
    recovery_run_to_artifact_response,
)
from backend.app.recovery.signatures import SYNTHETIC_START_MARKER, SYNTHETIC_END_MARKER
from backend.app.recovery.tracer import execute_traced_recovery


# ── Scenario 1: FULLY_RECOVERED RecoveryRun ──────────────────────────


def test_scenario_1_fully_recovered_adapter():
    """Scenario 1: Fully recovered evidence preserves V, R=0, M=0, status, confidence, and payload size."""
    content = b'{"case":"case_101","verified":true,"items":[1,2,3],"note":"forensic intact"}'
    run = execute_traced_recovery("intact_note.json", content)

    assert run.status == "FULLY_RECOVERED"
    assert run.total_verified_bytes == len(content)
    assert run.total_reconstructed_bytes == 0
    assert run.total_missing_bytes == 0

    artifact = recovery_run_to_artifact_response(run, case_id="case_101", artifact_id="art_custom_1")

    # API Identity & Case Link
    assert isinstance(artifact, ArtifactResponse)
    assert artifact.case_id == "case_101"
    assert artifact.artifact_id == "art_custom_1"
    assert artifact.format == run.format
    assert artifact.status == "FULLY_RECOVERED"

    # Byte Accounting & Provenance
    assert artifact.provenance.verified_bytes == run.total_verified_bytes
    assert artifact.provenance.reconstructed_bytes == 0
    assert artifact.provenance.missing_bytes == 0
    assert artifact.provenance.reconstruction_method in ["NONE", "JSON_STRUCTURAL_VALIDATION"]
    assert artifact.provenance.validation_status == "PASSED"

    # Actual Recovered Payload Sizing & Preview
    assert artifact.size_bytes == len(content)
    assert artifact.content_preview is not None
    assert "case_101" in artifact.content_preview

    # Confidence and Breakdown Contract
    assert isinstance(artifact.confidence_score, int)
    assert artifact.confidence_score == run.confidence["total"]
    bd = artifact.score_breakdown
    assert bd.total == artifact.confidence_score
    assert bd.total == (
        bd.header_validity
        + bd.footer_validity
        + bd.structural_validation
        + bd.size_plausibility
        + bd.reconstruction_integrity
    )

    # API Contract Null Placeholders
    assert artifact.category is None
    assert artifact.priority is None
    assert artifact.ai_summary is None


# ── Scenario 2: PARTIALLY_RECOVERED Fragmented Evidence ───────────────


def test_scenario_2_partially_recovered_fragmented_adapter():
    """Scenario 2: Fragmented evidence with missing gap preserves V, R, M, status, and accounting."""
    frag1 = SYNTHETIC_START_MARKER + b"FMT:txt;PART:1;" + b"Header block of text record."
    frag2 = SYNTHETIC_START_MARKER + b"FMT:txt;PART:2;" + b"Footer block of text record." + SYNTHETIC_END_MARKER
    gap = b"\x00" * 48
    content = frag1 + gap + frag2

    run = execute_traced_recovery("fragmented_record.txt", content)

    assert run.status == "PARTIALLY_RECOVERED"
    assert run.total_verified_bytes > 0
    assert run.total_missing_bytes > 0

    artifact = recovery_run_to_artifact_response(run, case_id="case_frag_99", artifact_id="art_frag_99")

    # Status & Provenance
    assert artifact.status == "PARTIALLY_RECOVERED"
    assert artifact.artifact_id == "art_frag_99"
    assert artifact.provenance.verified_bytes == run.total_verified_bytes
    assert artifact.provenance.reconstructed_bytes == run.total_reconstructed_bytes
    assert artifact.provenance.missing_bytes == run.total_missing_bytes
    assert artifact.provenance.missing_bytes > 0

    # No bytes lost or conflated during conversion: missing bytes never become recovered bytes
    assert (
        artifact.provenance.verified_bytes
        + artifact.provenance.reconstructed_bytes
        + artifact.provenance.missing_bytes
        == run.total_verified_bytes + run.total_reconstructed_bytes + run.total_missing_bytes
    )
    # size_bytes represents actual recovered payload bytes
    rec_bytes = extract_recovered_bytes(run)
    assert artifact.size_bytes == len(rec_bytes)
    assert artifact.size_bytes < (
        artifact.provenance.verified_bytes
        + artifact.provenance.reconstructed_bytes
        + artifact.provenance.missing_bytes
    )

    # Method & Metadata
    assert artifact.metadata["damage_region_count"] == len(run.damage_regions)
    assert artifact.metadata["fragment_count"] == len(run.fragments)
    assert artifact.metadata["run_id"] == run.run_id


# ── Scenario 3: PARTIALLY_RECOVERED Reconstructed JSON (R > 0) ────────


def test_scenario_3_reconstructed_json_adapter():
    """Scenario 3: Deterministically reconstructed JSON preserves R > 0 and reconstruction method."""
    truncated_json = b'{"report_id": 901, "findings": ["A", "B", "C"'
    run = execute_traced_recovery("audit.json", truncated_json)

    assert run.status == "PARTIALLY_RECOVERED"
    assert run.total_reconstructed_bytes > 0
    assert run.total_verified_bytes == len(truncated_json)

    artifact = recovery_run_to_artifact_response(run, case_id="case_json_audit", artifact_id="art_json_audit")

    # Honest R > 0 reporting
    assert artifact.status == "PARTIALLY_RECOVERED"
    assert artifact.artifact_id == "art_json_audit"
    assert artifact.provenance.reconstructed_bytes == run.total_reconstructed_bytes
    assert artifact.provenance.reconstructed_bytes == 2  # appended "]}"
    assert artifact.provenance.verified_bytes == len(truncated_json)
    assert artifact.provenance.missing_bytes == 0

    # Reconstruction method preserved
    assert "JSON" in artifact.provenance.reconstruction_method
    assert artifact.metadata["reconstruction_method"] == artifact.provenance.reconstruction_method

    # Sizing reflects actual recovered payload bytes
    assert artifact.size_bytes == len(truncated_json) + 2

    # Score breakdown integrity
    bd = artifact.score_breakdown
    assert bd.total == (
        bd.header_validity
        + bd.footer_validity
        + bd.structural_validation
        + bd.size_plausibility
        + bd.reconstruction_integrity
    )


# ── Scenario 4: UNRECOVERABLE RecoveryRun ─────────────────────────────


def test_scenario_4_unrecoverable_adapter():
    """Scenario 4: Unrecoverable evidence sets size_bytes=0, status=UNRECOVERABLE, FAILED validation."""
    garbage = b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f" * 16
    run = execute_traced_recovery("destroyed.bin", garbage)

    assert run.status == "UNRECOVERABLE"

    artifact = recovery_run_to_artifact_response(run, case_id="case_unrec", artifact_id="art_unrec")

    assert artifact.status == "UNRECOVERABLE"
    assert artifact.artifact_id == "art_unrec"
    assert artifact.size_bytes == 0
    assert artifact.content_preview is None
    assert artifact.confidence_score == 0
    assert artifact.score_breakdown.total == 0
    assert artifact.provenance.validation_status == "FAILED"
    assert artifact.provenance.verified_bytes == run.total_verified_bytes
    assert artifact.provenance.reconstructed_bytes == run.total_reconstructed_bytes
    assert artifact.provenance.missing_bytes == run.total_missing_bytes


# ── Scenario 5: Immutability Test ────────────────────────────────────


def test_scenario_5_immutability_of_input_recovery_run():
    """Scenario 5: Calling recovery_run_to_artifact_response must never mutate the input RecoveryRun."""
    truncated_json = b'{"test": 123, "arr": [1, 2'
    run = execute_traced_recovery("immutable.json", truncated_json)

    # Snapshot state prior to conversion
    run_dict_before = copy.deepcopy(run.model_dump())

    artifact1 = recovery_run_to_artifact_response(run, case_id="case_mut_1", artifact_id="art_mut_1")
    artifact2 = recovery_run_to_artifact_response(run, case_id="case_mut_2", artifact_id="art_mut_2")

    run_dict_after = run.model_dump()

    assert run_dict_before == run_dict_after, "RecoveryRun was mutated during adapter conversion!"
    assert artifact1.case_id == "case_mut_1"
    assert artifact2.case_id == "case_mut_2"
    assert artifact1.artifact_id == "art_mut_1"
    assert artifact2.artifact_id == "art_mut_2"


# ── Scenario 6: Honesty Test ─────────────────────────────────────────


def test_scenario_6_honesty_no_fabricated_bytes_or_altered_confidence():
    """Scenario 6: Adapter must never invent, estimate, or modify V/R/M byte counts or confidence."""
    # Handcrafted RecoveryRun with arbitrary forensic counts and existing artifact_id
    test_run = RecoveryRun(
        run_id="run_truth_test",
        artifact_id="art_origin",
        filename="custom_test.csv",
        format="csv",
        detection_mode="SIGNATURE",
        started_at=datetime.now(timezone.utc),
        total_input_bytes=500,
        total_verified_bytes=312,
        total_reconstructed_bytes=44,
        total_missing_bytes=144,
        confidence={
            "total": 68,
            "header_validity": 15,
            "footer_validity": 10,
            "structural_validation": 23,
            "size_plausibility": 10,
            "reconstruction_integrity": 10,
        },
        status="PARTIALLY_RECOVERED",
        provenance={
            "verified_bytes": 312,
            "reconstructed_bytes": 44,
            "missing_bytes": 144,
            "reconstruction_method": "CSV_DELIMITER_RECON",
        },
        validation={"valid": True, "method": "CSV_STRUCTURAL"},
        output={"recovered_bytes": (b"a,b,c\n1,2,3\n").hex()},
    )

    artifact = recovery_run_to_artifact_response(test_run, case_id="case_honest")

    # Inherits artifact_id directly from run
    assert artifact.artifact_id == "art_origin"

    # Byte counts must match exact input, not recomputed, rounded, or modified
    assert artifact.provenance.verified_bytes == 312
    assert artifact.provenance.reconstructed_bytes == 44
    assert artifact.provenance.missing_bytes == 144
    assert artifact.provenance.reconstruction_method == "CSV_DELIMITER_RECON"

    # Status must NOT be upgraded or downgraded
    assert artifact.status == "PARTIALLY_RECOVERED"

    # Confidence must map strictly to int, preserving total sum
    assert artifact.confidence_score == 68
    assert artifact.score_breakdown.total == 68
    bd = artifact.score_breakdown
    assert (
        bd.header_validity
        + bd.footer_validity
        + bd.structural_validation
        + bd.size_plausibility
        + bd.reconstruction_integrity
        == 68
    )


# ── Regression A: Missing artifact_id ─────────────────────────────────


def test_regression_a_missing_artifact_id_raises_value_error():
    """Regression A: When artifact_id is missing from both arguments and run, no UUID is fabricated."""
    run = RecoveryRun(
        run_id="run_no_art_id",
        artifact_id=None,
        filename="test.txt",
        format="txt",
        detection_mode="SIGNATURE",
        started_at=datetime.now(timezone.utc),
        total_input_bytes=10,
        total_verified_bytes=10,
        total_reconstructed_bytes=0,
        total_missing_bytes=0,
        confidence={"total": 100, "header_validity": 20, "footer_validity": 20, "structural_validation": 30, "size_plausibility": 15, "reconstruction_integrity": 15},
        status="FULLY_RECOVERED",
        output={"recovered_bytes": b"0123456789".hex()},
    )

    with pytest.raises(ValueError, match="artifact_id must be provided"):
        recovery_run_to_artifact_response(run, case_id="case_no_id")

    # When caller explicitly provides artifact_id, it is used
    art = recovery_run_to_artifact_response(run, case_id="case_provided", artifact_id="art_explicit")
    assert art.artifact_id == "art_explicit"


# ── Regression B: Confidence Preservation and Representation ─────────


def test_regression_b_canonical_integer_confidence_preserved_exactly():
    """Regression B1: Canonical integer confidence scores are preserved with zero modification."""
    run = RecoveryRun(
        run_id="run_int_conf",
        artifact_id="art_int_conf",
        filename="test.txt",
        format="txt",
        detection_mode="SIGNATURE",
        started_at=datetime.now(timezone.utc),
        total_input_bytes=10,
        total_verified_bytes=10,
        total_reconstructed_bytes=0,
        total_missing_bytes=0,
        confidence={
            "total": 95,
            "header_validity": 20,
            "footer_validity": 20,
            "structural_validation": 25,
            "size_plausibility": 15,
            "reconstruction_integrity": 15,
        },
        status="FULLY_RECOVERED",
        output={"recovered_bytes": b"0123456789".hex()},
    )

    art = recovery_run_to_artifact_response(run, case_id="case_conf")
    assert art.confidence_score == 95
    assert art.score_breakdown.total == 95
    assert art.score_breakdown.header_validity == 20
    assert art.score_breakdown.footer_validity == 20
    assert art.score_breakdown.structural_validation == 25
    assert art.score_breakdown.size_plausibility == 15
    assert art.score_breakdown.reconstruction_integrity == 15


def test_regression_b_float_representation_conversion_satisfies_schema():
    """Regression B2: When floats are provided, documented integer conversion preserves component sum == total."""
    score, bd = _compute_score_breakdown_schema(
        {
            "total": 68.4,
            "header_validity": 15.1,
            "footer_validity": 10.0,
            "structural_validation": 23.3,
            "size_plausibility": 10.0,
            "reconstruction_integrity": 10.0,
        },
        "PARTIALLY_RECOVERED",
    )
    assert score == 68
    assert bd.total == 68
    assert (
        bd.header_validity
        + bd.footer_validity
        + bd.structural_validation
        + bd.size_plausibility
        + bd.reconstruction_integrity
        == 68
    )


# ── Regression C: size_bytes Never Fabricates Payload from V + R ──────


def test_regression_c_size_bytes_never_fabricates_payload_from_v_plus_r():
    """Regression C: When V + R > 0 exists but recovered_bytes are unavailable, size_bytes is 0."""
    run = RecoveryRun(
        run_id="run_missing_payload",
        artifact_id="art_no_payload",
        filename="corrupted.bin",
        format="bin",
        detection_mode="SIGNATURE",
        started_at=datetime.now(timezone.utc),
        total_input_bytes=400,
        total_verified_bytes=300,
        total_reconstructed_bytes=50,
        total_missing_bytes=50,
        confidence={"total": 50, "header_validity": 10, "footer_validity": 10, "structural_validation": 15, "size_plausibility": 10, "reconstruction_integrity": 5},
        status="PARTIALLY_RECOVERED",
        output=None,  # No actual recovered payload available!
    )

    art = recovery_run_to_artifact_response(run, case_id="case_no_payload")

    # size_bytes must NOT falsely claim 350 bytes (V + R)
    assert art.size_bytes == 0
    assert art.content_preview is None

    # Provenance retains full truthful accounting
    assert art.provenance.verified_bytes == 300
    assert art.provenance.reconstructed_bytes == 50
    assert art.provenance.missing_bytes == 50


# ── Edge Cases ────────────────────────────────────────────────────────


def test_extract_recovered_bytes_edge_cases():
    """Verify extract_recovered_bytes handles None output, missing hex, and malformed hex safely."""
    run_empty = RecoveryRun(
        run_id="run_empty",
        filename="test.txt",
        format="txt",
        detection_mode="SIGNATURE",
        started_at=datetime.now(timezone.utc),
        total_input_bytes=0,
        total_verified_bytes=0,
        total_reconstructed_bytes=0,
        total_missing_bytes=0,
        confidence={},
        status="UNRECOVERABLE",
        output=None,
    )
    assert extract_recovered_bytes(run_empty) == b""

    run_malformed_hex = RecoveryRun(
        run_id="run_bad_hex",
        filename="test.txt",
        format="txt",
        detection_mode="SIGNATURE",
        started_at=datetime.now(timezone.utc),
        total_input_bytes=10,
        total_verified_bytes=10,
        total_reconstructed_bytes=0,
        total_missing_bytes=0,
        confidence={},
        status="FULLY_RECOVERED",
        output={"recovered_bytes": "not-valid-hex!"},
    )
    assert extract_recovered_bytes(run_malformed_hex) == b""


def test_compute_score_breakdown_schema_edge_cases():
    """Verify breakdown computation when confidence dict is missing or empty defaults honestly to 0."""
    score, bd = _compute_score_breakdown_schema(None, "UNRECOVERABLE")
    assert score == 0
    assert bd.total == 0

    score, bd = _compute_score_breakdown_schema({}, "FULLY_RECOVERED")
    assert score == 0
    assert bd.total == 0
    assert bd.header_validity == 0
    assert bd.structural_validation == 0
