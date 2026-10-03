"""tests/test_benchmark_harness.py — Comprehensive Unit & Coordinate Tests for Benchmark Harness.

Verifies:
1. Five explicit coordinate tests (Contiguous, Truncated, Packed Gap, Bifragment, Reconstructed)
   - Proves recovered payload offsets cannot be confused with original offsets.
2. Candidate matching (One-to-one, duplicates, deterministic tie-breaking, unbounded)
3. Expectation oracle & status truth table (Intact, Gap, Deterministic Repair, Corruption, Unrecoverable)
4. Metrics (Volume accuracy, Interval IoU, Byte correctness, Zero-safe relationships)
5. False-recovery auditor (All 6 forensic violation rules)
6. Model invariants (Placement ordering, coordinate bounds, cross-buffer rejection)
"""

from __future__ import annotations

import base64
import hashlib
import pytest

from benchmark.models import (
    BenchmarkGroundTruthManifest,
    BenchmarkObservedManifest,
    ObservedArtifactRecoveryResult,
    ObservedCandidateResult,
    ObservedRecoverySegment,
    ObservedRelationshipRecord,
    PhysicalArtifactRecord,
    PhysicalDamageInterval,
    PhysicalPlacement,
    PhysicalRelationshipRecord,
)
from benchmark.matcher import (
    compute_span_iou,
    match_candidates_one_to_one,
)
from benchmark.expectations import (
    derive_expected_recovery,
)
from benchmark.metrics import (
    compute_interval_iou,
    compute_relationship_accuracy,
    compute_volume_ratio,
    compute_evaluation_metrics,
)
from benchmark.evaluator import (
    audit_false_recovery,
    evaluate_scenario,
)


# ── HELPER FACTORIES ────────────────────────────────────────────────────────

def _make_artifact(
    artifact_id: str = "art-01",
    payload: bytes = b"0123456789" * 10,  # 100 bytes
    header_offset: int = 0,
    placements: list[PhysicalPlacement] | None = None,
    damage: list[PhysicalDamageInterval] | None = None,
    is_unrecoverable: bool = False,
    fmt: str = "txt",
) -> PhysicalArtifactRecord:
    size = len(payload)
    sha = hashlib.sha256(payload).hexdigest()
    b64 = base64.b64encode(payload).decode("ascii")
    if placements is None:
        placements = [
            PhysicalPlacement(
                fragment_index=0,
                evidence_offset=header_offset,
                evidence_length=size,
                original_offset=0,
            )
        ]
    return PhysicalArtifactRecord(
        artifact_id=artifact_id,
        original_filename=f"{artifact_id}.{fmt}",
        format=fmt,
        original_size_bytes=size,
        original_sha256=sha,
        original_bytes_b64=b64,
        header_evidence_offset=header_offset,
        placements=placements,
        damage_intervals=damage or [],
        is_unrecoverable=is_unrecoverable,
    )


# ═════════════════════════════════════════════════════════════════════════════
# 1. FIVE EXPLICIT COORDINATE TESTS (P0-1)
# ═════════════════════════════════════════════════════════════════════════════

def test_coordinate_01_contiguous_artifact():
    """1. Contiguous artifact: E=[500, 600), O=[0, 100), R=[0, 100)."""
    payload = b"A" * 100
    art = _make_artifact(
        header_offset=500,
        payload=payload,
        placements=[
            PhysicalPlacement(
                fragment_index=0,
                evidence_offset=500,
                evidence_length=100,
                original_offset=0,
            )
        ],
    )
    seg = ObservedRecoverySegment(
        segment_id="seg-1",
        category="VERIFIED",
        evidence_start=500,
        evidence_end=600,
        original_start=0,
        original_end=100,
        recovered_start=0,
        recovered_end=100,
    )
    recovery = ObservedArtifactRecoveryResult(
        detected_format="txt",
        observed_status="FULLY_RECOVERED",
        confidence_score=100,
        total_input_bytes=100,
        total_verified_bytes=100,
        total_reconstructed_bytes=0,
        total_missing_bytes=0,
        recovered_payload_bytes=payload,
        verified_segments=[seg],
    )
    exp = derive_expected_recovery(art)
    metrics = compute_evaluation_metrics(art, exp, recovery)
    violations = audit_false_recovery(art, recovery, exp)

    assert metrics.v_byte_correctness == 1.0
    assert metrics.v_interval_iou == 1.0
    assert len(violations) == 0


def test_coordinate_02_truncated_artifact():
    """2. Truncated artifact: Verified [0, 70), Missing suffix [70, 100)."""
    full_payload = b"B" * 100
    truncated_payload = b"B" * 70
    damage = [
        PhysicalDamageInterval(
            original_start=70,
            original_end=100,
            length=30,
            damage_type="PHYSICAL_GAP",
            reconstruction_mode="RECONSTRUCTION_NONE",
        )
    ]
    art = _make_artifact(
        payload=full_payload,
        header_offset=500,
        placements=[
            PhysicalPlacement(
                fragment_index=0,
                evidence_offset=500,
                evidence_length=70,
                original_offset=0,
            )
        ],
        damage=damage,
    )
    v_seg = ObservedRecoverySegment(
        segment_id="seg-1",
        category="VERIFIED",
        evidence_start=500,
        evidence_end=570,
        original_start=0,
        original_end=70,
        recovered_start=0,
        recovered_end=70,
    )
    m_seg = ObservedRecoverySegment(
        segment_id="seg-2",
        category="MISSING",
        original_start=70,
        original_end=100,
    )
    recovery = ObservedArtifactRecoveryResult(
        detected_format="txt",
        observed_status="PARTIALLY_RECOVERED",
        confidence_score=70,
        total_input_bytes=70,
        total_verified_bytes=70,
        total_reconstructed_bytes=0,
        total_missing_bytes=30,
        recovered_payload_bytes=truncated_payload,
        verified_segments=[v_seg],
        missing_segments=[m_seg],
    )
    exp = derive_expected_recovery(art)
    metrics = compute_evaluation_metrics(art, exp, recovery)
    violations = audit_false_recovery(art, recovery, exp)

    assert metrics.v_byte_correctness == 1.0
    assert metrics.v_interval_iou == 1.0
    assert metrics.m_interval_iou == 1.0
    assert metrics.observed_status == "PARTIALLY_RECOVERED"
    assert len(violations) == 0


def test_coordinate_03_single_physical_gap_packed_concatenation():
    """3. CRITICAL TEST: Single physical gap in packed concatenation.

    Original: 100 bytes.
      Fragment A: 0..40 (40 bytes of 'A')
      Physical Gap: 40..60 (20 bytes of 'X' - MISSING)
      Fragment B: 60..100 (40 bytes of 'B')

    Evidence: 80 bytes packed: Fragment A + Fragment B [0..80).
    Recovered Payload: 80 bytes [0..80):
      Payload 0..40 is 'A' (Fragment A)
      Payload 40..80 is 'B' (Fragment B)

    CRITICAL PROOF:
      payload[40:80] == original[60:100] == b'B' * 40
      payload[40:80] != original[40:80] (which is b'X'*20 + b'B'*20)
    """
    orig_bytes = (b"A" * 40) + (b"X" * 20) + (b"B" * 40)  # 100 bytes
    recovered_payload = (b"A" * 40) + (b"B" * 40)         # 80 bytes

    # Verify our test setup premise
    assert recovered_payload[40:80] == orig_bytes[60:100]
    assert recovered_payload[40:80] != orig_bytes[40:80]

    art = _make_artifact(
        payload=orig_bytes,
        header_offset=0,
        placements=[
            PhysicalPlacement(fragment_index=0, evidence_offset=0, evidence_length=40, original_offset=0),
            PhysicalPlacement(fragment_index=1, evidence_offset=40, evidence_length=40, original_offset=60),
        ],
        damage=[
            PhysicalDamageInterval(
                original_start=40,
                original_end=60,
                length=20,
                damage_type="PHYSICAL_GAP",
                reconstruction_mode="RECONSTRUCTION_NONE",
            )
        ],
    )

    seg_a = ObservedRecoverySegment(
        segment_id="seg-a",
        category="VERIFIED",
        evidence_start=0,
        evidence_end=40,
        original_start=0,
        original_end=40,
        recovered_start=0,
        recovered_end=40,
    )
    seg_b = ObservedRecoverySegment(
        segment_id="seg-b",
        category="VERIFIED",
        evidence_start=40,
        evidence_end=80,
        original_start=60,
        original_end=100,
        recovered_start=40,
        recovered_end=80,
    )
    seg_gap = ObservedRecoverySegment(
        segment_id="seg-gap",
        category="MISSING",
        original_start=40,
        original_end=60,
    )

    recovery = ObservedArtifactRecoveryResult(
        detected_format="txt",
        observed_status="PARTIALLY_RECOVERED",
        confidence_score=80,
        total_input_bytes=80,
        total_verified_bytes=80,
        total_reconstructed_bytes=0,
        total_missing_bytes=20,
        recovered_payload_bytes=recovered_payload,
        verified_segments=[seg_a, seg_b],
        missing_segments=[seg_gap],
    )

    exp = derive_expected_recovery(art)
    metrics = compute_evaluation_metrics(art, exp, recovery)
    violations = audit_false_recovery(art, recovery, exp)

    # If the evaluator had used recovered offsets (40:80) to index original,
    # v_byte_correctness would fail. Because it used original coordinates (60:100), it passes 100%!
    assert metrics.v_byte_correctness == 1.0
    assert metrics.v_interval_iou == 1.0
    assert metrics.m_interval_iou == 1.0
    assert len(violations) == 0


def test_coordinate_04_bifragment_sparse_evidence():
    """4. Bifragment sparse evidence: non-contiguous evidence coordinates."""
    orig_bytes = (b"C" * 40) + (b"D" * 60)  # 100 bytes
    art = _make_artifact(
        payload=orig_bytes,
        header_offset=1000,
        placements=[
            PhysicalPlacement(fragment_index=0, evidence_offset=1000, evidence_length=40, original_offset=0),
            PhysicalPlacement(fragment_index=1, evidence_offset=2000, evidence_length=60, original_offset=40),
        ],
    )

    seg_1 = ObservedRecoverySegment(
        segment_id="seg-1",
        category="VERIFIED",
        evidence_start=1000,
        evidence_end=1040,
        original_start=0,
        original_end=40,
        recovered_start=0,
        recovered_end=40,
    )
    seg_2 = ObservedRecoverySegment(
        segment_id="seg-2",
        category="VERIFIED",
        evidence_start=2000,
        evidence_end=2060,
        original_start=40,
        original_end=100,
        recovered_start=40,
        recovered_end=100,
    )

    recovery = ObservedArtifactRecoveryResult(
        detected_format="txt",
        observed_status="FULLY_RECOVERED",
        confidence_score=100,
        total_input_bytes=100,
        total_verified_bytes=100,
        total_reconstructed_bytes=0,
        total_missing_bytes=0,
        recovered_payload_bytes=orig_bytes,
        verified_segments=[seg_1, seg_2],
    )

    exp = derive_expected_recovery(art)
    metrics = compute_evaluation_metrics(art, exp, recovery)
    violations = audit_false_recovery(art, recovery, exp)

    assert metrics.v_byte_correctness == 1.0
    assert len(violations) == 0


def test_coordinate_05_reconstructed_region():
    """5. Reconstructed region: structural repair in payload compared against expected repair."""
    orig_json = b'{"status": "ok"}'  # 16 bytes. Last byte '}' is at original [15, 16)
    expected_repair = b"}"
    expected_repair_b64 = base64.b64encode(expected_repair).decode("ascii")

    art = _make_artifact(
        payload=orig_json,
        header_offset=0,
        fmt="json",
        placements=[
            PhysicalPlacement(fragment_index=0, evidence_offset=0, evidence_length=15, original_offset=0),
        ],
        damage=[
            PhysicalDamageInterval(
                original_start=15,
                original_end=16,
                length=1,
                damage_type="PHYSICAL_GAP",
                reconstruction_mode="RECONSTRUCTION_DETERMINISTIC",
                expected_reconstructed_bytes_b64=expected_repair_b64,
            )
        ],
    )

    v_seg = ObservedRecoverySegment(
        segment_id="v-1",
        category="VERIFIED",
        evidence_start=0,
        evidence_end=15,
        original_start=0,
        original_end=15,
        recovered_start=0,
        recovered_end=15,
    )
    r_seg = ObservedRecoverySegment(
        segment_id="r-1",
        category="RECONSTRUCTED",
        original_start=15,
        original_end=16,
        recovered_start=15,
        recovered_end=16,
    )

    recovery = ObservedArtifactRecoveryResult(
        detected_format="json",
        observed_status="PARTIALLY_RECOVERED",
        confidence_score=95,
        total_input_bytes=15,
        total_verified_bytes=15,
        total_reconstructed_bytes=1,
        total_missing_bytes=0,
        recovered_payload_bytes=orig_json,
        verified_segments=[v_seg],
        reconstructed_segments=[r_seg],
    )

    exp = derive_expected_recovery(art)
    assert exp.expected_status == "PARTIALLY_RECOVERED"
    assert exp.expected_reconstructed_bytes == 1

    metrics = compute_evaluation_metrics(art, exp, recovery)
    violations = audit_false_recovery(art, recovery, exp)

    assert metrics.v_byte_correctness == 1.0
    assert metrics.r_byte_correctness == 1.0
    assert metrics.r_interval_iou == 1.0
    assert len(violations) == 0


# ═════════════════════════════════════════════════════════════════════════════
# 2. CANDIDATE MATCHING TESTS (P1-3)
# ═════════════════════════════════════════════════════════════════════════════

def test_matcher_one_to_one():
    art1 = _make_artifact("art-1", header_offset=100)
    art2 = _make_artifact("art-2", header_offset=500)
    cand1 = ObservedCandidateResult(candidate_id="c-1", evidence_buffer_id="buf-1", format="txt", offset=100, detected_header_length=4, estimated_end_offset=200)
    cand2 = ObservedCandidateResult(candidate_id="c-2", evidence_buffer_id="buf-1", format="txt", offset=500, detected_header_length=4, estimated_end_offset=600)

    res = match_candidates_one_to_one([art1, art2], [cand1, cand2], evidence_buffer_id="buf-1")
    assert res.true_positives == 2
    assert res.false_positives == 0
    assert res.false_negatives == 0
    assert res.precision == 1.0
    assert res.recall == 1.0


def test_matcher_duplicate_candidates():
    """Verify duplicate candidates claiming the same GT artifact become FPs."""
    art = _make_artifact("art-1", header_offset=100)
    cand1 = ObservedCandidateResult(candidate_id="c-1", evidence_buffer_id="buf-1", format="txt", offset=100, detected_header_length=4, estimated_end_offset=200)
    cand_dup = ObservedCandidateResult(candidate_id="c-dup", evidence_buffer_id="buf-1", format="txt", offset=100, detected_header_length=4, estimated_end_offset=180)

    res = match_candidates_one_to_one([art], [cand1, cand_dup], evidence_buffer_id="buf-1")
    assert res.true_positives == 1
    assert res.false_positives == 1
    assert len(res.duplicate_candidates) == 1
    assert res.duplicate_candidates[0].candidate_id == "c-dup"
    assert res.precision == 0.5
    assert res.recall == 1.0


def test_matcher_deterministic_tie_breaking():
    art = _make_artifact("art-1", header_offset=100)
    # Two identical candidates except for candidate_id string
    c_b = ObservedCandidateResult(candidate_id="cand-b", evidence_buffer_id="buf-1", format="txt", offset=100, detected_header_length=4, estimated_end_offset=200)
    c_a = ObservedCandidateResult(candidate_id="cand-a", evidence_buffer_id="buf-1", format="txt", offset=100, detected_header_length=4, estimated_end_offset=200)

    res = match_candidates_one_to_one([art], [c_b, c_a], evidence_buffer_id="buf-1")
    assert res.matched_pairs[0].candidate.candidate_id == "cand-a"


def test_matcher_unbounded_candidate():
    art = _make_artifact("art-1", header_offset=100)
    cand = ObservedCandidateResult(candidate_id="c-unb", evidence_buffer_id="buf-1", format="txt", offset=100, detected_header_length=4, estimated_end_offset=None, is_unbounded=True)

    res = match_candidates_one_to_one([art], [cand], evidence_buffer_id="buf-1")
    assert res.true_positives == 1
    assert res.matched_pairs[0].candidate.is_unbounded is True


# ═════════════════════════════════════════════════════════════════════════════
# 3. EXPECTATION ORACLE & STATUS TRUTH TABLE (P1-5)
# ═════════════════════════════════════════════════════════════════════════════

def test_expectation_intact():
    art = _make_artifact()
    exp = derive_expected_recovery(art)
    assert exp.expected_status == "FULLY_RECOVERED"
    assert exp.expected_verified_bytes == 100
    assert exp.expected_reconstructed_bytes == 0
    assert exp.expected_missing_bytes == 0


def test_expectation_physical_gap():
    damage = [PhysicalDamageInterval(original_start=20, original_end=50, length=30, damage_type="PHYSICAL_GAP")]
    art = _make_artifact(damage=damage)
    exp = derive_expected_recovery(art)
    assert exp.expected_status == "PARTIALLY_RECOVERED"
    assert exp.expected_missing_bytes == 30


def test_expectation_deterministic_repair():
    damage = [
        PhysicalDamageInterval(
            original_start=90, original_end=100, length=10,
            damage_type="PHYSICAL_GAP",
            reconstruction_mode="RECONSTRUCTION_DETERMINISTIC",
            expected_reconstructed_bytes_b64=base64.b64encode(b"Z" * 10).decode("ascii"),
        )
    ]
    art = _make_artifact(damage=damage)
    exp = derive_expected_recovery(art)
    assert exp.expected_status == "PARTIALLY_RECOVERED"
    assert exp.expected_reconstructed_bytes == 10


def test_expectation_unrepairable_corruption():
    damage = [PhysicalDamageInterval(original_start=10, original_end=30, length=20, damage_type="BIT_FLIP")]
    art = _make_artifact(damage=damage)
    exp = derive_expected_recovery(art)
    assert exp.expected_status == "CORRUPTED"


def test_expectation_explicit_unrecoverable():
    art = _make_artifact(is_unrecoverable=True)
    exp = derive_expected_recovery(art)
    assert exp.expected_status == "UNRECOVERABLE"
    assert exp.expected_verified_bytes == 0
    assert exp.expected_missing_bytes == 100


# ═════════════════════════════════════════════════════════════════════════════
# 4. METRICS & ZERO-RELATIONSHIP TESTS (P2-6)
# ═════════════════════════════════════════════════════════════════════════════

def test_volume_accuracy_decoupled_from_coordinates():
    """Prove that volume accuracy and interval IoU are strictly decoupled."""
    # Volume is identical (100 vs 100 -> ratio 1.0)
    vol_acc = compute_volume_ratio(100, 100)
    assert vol_acc == 1.0

    # But spatial intervals are completely disjoint [0, 100) vs [200, 300) -> IoU 0.0
    iou = compute_interval_iou([(0, 100)], [(200, 300)])
    assert iou == 0.0


def test_zero_relationship_accuracy():
    """Verify zero-relationship handling (P2-6)."""
    # 0 GT, 0 Observed -> 1.0
    assert compute_relationship_accuracy([], []) == 1.0

    # 0 GT, >0 Observed -> 0.0 (Phantom edges)
    obs_rel = [ObservedRelationshipRecord(evidence_buffer_id="buf-1", source_candidate_id="c1", target_candidate_id="c2", relationship_type="CONTAINS")]
    assert compute_relationship_accuracy([], obs_rel) == 0.0

    # >0 GT, 1 matching TP -> 1.0
    gt_rel = [PhysicalRelationshipRecord(evidence_buffer_id="buf-1", source_artifact_id="c1", target_artifact_id="c2", relationship_type="CONTAINS")]
    assert compute_relationship_accuracy(gt_rel, obs_rel) == 1.0


# ═════════════════════════════════════════════════════════════════════════════
# 5. FALSE-RECOVERY AUDITOR TESTS
# ═════════════════════════════════════════════════════════════════════════════

def test_audit_damaged_marked_fully_recovered():
    damage = [PhysicalDamageInterval(original_start=50, original_end=70, length=20, damage_type="PHYSICAL_GAP")]
    art = _make_artifact(damage=damage)
    exp = derive_expected_recovery(art)

    recovery = ObservedArtifactRecoveryResult(
        detected_format="txt",
        observed_status="FULLY_RECOVERED",  # FALSE FULLY RECOVERED!
        confidence_score=100,
        total_input_bytes=80,
        total_verified_bytes=80,
        total_reconstructed_bytes=0,
        total_missing_bytes=20,
    )
    violations = audit_false_recovery(art, recovery, exp)
    assert any("FALSE_FULLY_RECOVERED" in v for v in violations)


def test_audit_reconstructed_marked_fully_recovered():
    art = _make_artifact()
    exp = derive_expected_recovery(art)
    recovery = ObservedArtifactRecoveryResult(
        detected_format="txt",
        observed_status="FULLY_RECOVERED",  # VIOLATION: R > 0 with FULLY_RECOVERED
        confidence_score=100,
        total_input_bytes=100,
        total_verified_bytes=90,
        total_reconstructed_bytes=10,
        total_missing_bytes=0,
    )
    violations = audit_false_recovery(art, recovery, exp)
    assert any("INVALID_STATUS_INVARIANT" in v for v in violations)


def test_audit_unaccounted_physical_gap():
    damage = [PhysicalDamageInterval(original_start=50, original_end=70, length=20, damage_type="PHYSICAL_GAP")]
    art = _make_artifact(damage=damage)
    exp = derive_expected_recovery(art)
    recovery = ObservedArtifactRecoveryResult(
        detected_format="txt",
        observed_status="PARTIALLY_RECOVERED",
        confidence_score=80,
        total_input_bytes=80,
        total_verified_bytes=80,
        total_reconstructed_bytes=0,
        total_missing_bytes=0,  # VIOLATION: Missing bytes omitted!
    )
    violations = audit_false_recovery(art, recovery, exp)
    assert any("UNACCOUNTED_GAP" in v for v in violations)


def test_audit_overstated_verified_bytes():
    art = _make_artifact(payload=b"A" * 100)
    exp = derive_expected_recovery(art)
    recovery = ObservedArtifactRecoveryResult(
        detected_format="txt",
        observed_status="FULLY_RECOVERED",
        confidence_score=100,
        total_input_bytes=100,
        total_verified_bytes=120,  # VIOLATION: 120 > 100 surviving
        total_reconstructed_bytes=0,
        total_missing_bytes=0,
    )
    violations = audit_false_recovery(art, recovery, exp)
    assert any("OVERSTATED_VERIFICATION" in v for v in violations)


def test_audit_divergent_verified_bytes():
    orig_payload = b"ORIGINAL" * 10
    altered_payload = b"MUTATED!" * 10
    art = _make_artifact(payload=orig_payload)
    exp = derive_expected_recovery(art)

    seg = ObservedRecoverySegment(
        segment_id="s1",
        category="VERIFIED",
        evidence_start=0, evidence_end=80,
        original_start=0, original_end=80,
        recovered_start=0, recovered_end=80,
    )
    recovery = ObservedArtifactRecoveryResult(
        detected_format="txt",
        observed_status="FULLY_RECOVERED",
        confidence_score=100,
        total_input_bytes=80,
        total_verified_bytes=80,
        total_reconstructed_bytes=0,
        total_missing_bytes=0,
        recovered_payload_bytes=altered_payload,
        verified_segments=[seg],
    )
    violations = audit_false_recovery(art, recovery, exp)
    assert any("FALSE_VERIFIED_BYTES" in v for v in violations)


# ═════════════════════════════════════════════════════════════════════════════
# 6. MODEL VALIDATION & INVARIANT TESTS (P1-4)
# ═════════════════════════════════════════════════════════════════════════════

def test_model_placement_ordering_enforced():
    """Verify that unsorted placements raise a validation error."""
    with pytest.raises(ValueError, match="Placements must be strictly sorted"):
        _make_artifact(
            placements=[
                PhysicalPlacement(fragment_index=1, evidence_offset=500, evidence_length=40, original_offset=60),
                PhysicalPlacement(fragment_index=0, evidence_offset=100, evidence_length=40, original_offset=0),
            ]
        )


def test_model_header_offset_mismatch_rejected():
    with pytest.raises(ValueError, match="header_evidence_offset .* must match first placement"):
        _make_artifact(
            header_offset=999,
            placements=[
                PhysicalPlacement(fragment_index=0, evidence_offset=100, evidence_length=100, original_offset=0),
            ],
        )


def test_model_cross_buffer_relationship_rejected():
    art = _make_artifact()
    with pytest.raises(ValueError, match="Relationship evidence_buffer_id .* does not match"):
        BenchmarkGroundTruthManifest(
            scenario_id="scen-1",
            evidence_buffer_id="buf-A",
            evidence_size_bytes=100,
            evidence_sha256="a" * 64,
            seed=42,
            artifacts=[art],
            spatial_relationships=[
                PhysicalRelationshipRecord(
                    evidence_buffer_id="buf-B",  # MISMATCH!
                    source_artifact_id="art-01",
                    target_artifact_id="art-02",
                    relationship_type="CONTAINS",
                )
            ],
        )


def test_model_invalid_coordinate_ranges_rejected():
    """Verify that invalid coordinates raise validation errors."""
    with pytest.raises(ValueError, match="evidence_start must be non-negative"):
        ObservedRecoverySegment(
            segment_id="bad-1",
            category="VERIFIED",
            evidence_start=-5,
            evidence_end=10,
            original_start=0,
            original_end=15,
            recovered_start=0,
            recovered_end=15,
        )

    with pytest.raises(ValueError, match="recovered_end .* must be >= .*recovered_start"):
        ObservedRecoverySegment(
            segment_id="bad-2",
            category="VERIFIED",
            evidence_start=0,
            evidence_end=10,
            original_start=0,
            original_end=10,
            recovered_start=20,
            recovered_end=10,  # END < START!
        )

    with pytest.raises(ValueError, match="VERIFIED segment length mismatch"):
        ObservedRecoverySegment(
            segment_id="bad-3",
            category="VERIFIED",
            evidence_start=0,
            evidence_end=10,
            original_start=0,
            original_end=10,
            recovered_start=0,
            recovered_end=20,  # 10 != 20!
        )


def test_matcher_multiple_evidence_buffers():
    """Verify candidates and artifacts in different evidence buffers do not match."""
    art = _make_artifact("art-1", header_offset=100)
    cand_wrong_buf = ObservedCandidateResult(
        candidate_id="c-diff",
        evidence_buffer_id="buf-OTHER",
        format="txt",
        offset=100,
        detected_header_length=4,
        estimated_end_offset=200,
    )
    res = match_candidates_one_to_one([art], [cand_wrong_buf], evidence_buffer_id="buf-MAIN")
    assert res.true_positives == 0
    assert res.false_positives == 1
    assert res.false_negatives == 1


def test_evaluator_end_to_end_scenario():
    """Test full evaluate_scenario execution on a complete ground-truth and observed manifest."""
    art = _make_artifact("art-1", header_offset=0, payload=b"Hello World" * 5)
    gt_manifest = BenchmarkGroundTruthManifest(
        scenario_id="scen-e2e-01",
        evidence_buffer_id="buf-1",
        evidence_size_bytes=len(art.original_bytes),
        evidence_sha256=hashlib.sha256(art.original_bytes).hexdigest(),
        seed=42,
        artifacts=[art],
    )
    cand = ObservedCandidateResult(
        candidate_id="c-1",
        evidence_buffer_id="buf-1",
        format="txt",
        offset=0,
        detected_header_length=5,
        estimated_end_offset=len(art.original_bytes),
    )
    seg = ObservedRecoverySegment(
        segment_id="s-1",
        category="VERIFIED",
        evidence_start=0,
        evidence_end=len(art.original_bytes),
        original_start=0,
        original_end=len(art.original_bytes),
        recovered_start=0,
        recovered_end=len(art.original_bytes),
    )
    recovery = ObservedArtifactRecoveryResult(
        observed_candidate_id="c-1",
        detected_format="txt",
        observed_status="FULLY_RECOVERED",
        confidence_score=100,
        total_input_bytes=len(art.original_bytes),
        total_verified_bytes=len(art.original_bytes),
        total_reconstructed_bytes=0,
        total_missing_bytes=0,
        recovered_payload_bytes=art.original_bytes,
        verified_segments=[seg],
    )
    observed_manifest = BenchmarkObservedManifest(
        scenario_id="scen-e2e-01",
        evidence_buffer_id="buf-1",
        candidates=[cand],
        recoveries=[recovery],
    )

    report = evaluate_scenario(gt_manifest, observed_manifest)
    assert report.scenario_id == "scen-e2e-01"
    assert report.candidate_metrics.precision == 1.0
    assert report.candidate_metrics.recall == 1.0
    assert report.relationship_accuracy == 1.0
    assert len(report.artifact_evaluations) == 1
    assert report.artifact_evaluations[0].v_byte_correctness == 1.0
    assert report.artifact_evaluations[0].status_match is True
    assert report.has_false_fully_recovered is False
    assert report.passed is True


def test_reconstructed_byte_correctness_exact_match_and_mismatch():
    """Verify reconstructed byte correctness reports 1.0 for match and 0.0 for mismatch."""
    orig_json = b'{"status": "ok"}'
    expected_repair = b"}"
    expected_repair_b64 = base64.b64encode(expected_repair).decode("ascii")

    art = _make_artifact(
        payload=orig_json,
        header_offset=0,
        fmt="json",
        placements=[
            PhysicalPlacement(fragment_index=0, evidence_offset=0, evidence_length=15, original_offset=0),
        ],
        damage=[
            PhysicalDamageInterval(
                original_start=15,
                original_end=16,
                length=1,
                damage_type="PHYSICAL_GAP",
                reconstruction_mode="RECONSTRUCTION_DETERMINISTIC",
                expected_reconstructed_bytes_b64=expected_repair_b64,
            )
        ],
    )
    exp = derive_expected_recovery(art)

    # Case A: Correct reconstruction (b"}")
    payload_correct = b'{"status": "ok"}'
    seg_v = ObservedRecoverySegment(
        segment_id="v-1", category="VERIFIED",
        evidence_start=0, evidence_end=15,
        original_start=0, original_end=15,
        recovered_start=0, recovered_end=15,
    )
    seg_r_correct = ObservedRecoverySegment(
        segment_id="r-1", category="RECONSTRUCTED",
        original_start=15, original_end=16,
        recovered_start=15, recovered_end=16,
    )
    rec_correct = ObservedArtifactRecoveryResult(
        detected_format="json",
        observed_status="PARTIALLY_RECOVERED",
        confidence_score=95,
        total_input_bytes=15,
        total_verified_bytes=15,
        total_reconstructed_bytes=1,
        total_missing_bytes=0,
        recovered_payload_bytes=payload_correct,
        verified_segments=[seg_v],
        reconstructed_segments=[seg_r_correct],
    )
    metrics_correct = compute_evaluation_metrics(art, exp, rec_correct)
    violations_correct = audit_false_recovery(art, rec_correct, exp)
    assert metrics_correct.r_byte_correctness == 1.0
    assert len(violations_correct) == 0

    # Case B: Incorrect reconstruction (b"]" instead of b"}")
    payload_incorrect = b'{"status": "ok"]'
    rec_incorrect = ObservedArtifactRecoveryResult(
        detected_format="json",
        observed_status="PARTIALLY_RECOVERED",
        confidence_score=95,
        total_input_bytes=15,
        total_verified_bytes=15,
        total_reconstructed_bytes=1,
        total_missing_bytes=0,
        recovered_payload_bytes=payload_incorrect,
        verified_segments=[seg_v],
        reconstructed_segments=[seg_r_correct],
    )
    metrics_incorrect = compute_evaluation_metrics(art, exp, rec_incorrect)
    violations_incorrect = audit_false_recovery(art, rec_incorrect, exp)
    assert metrics_incorrect.r_byte_correctness == 0.0
    assert any("FALSE_RECONSTRUCTED_BYTES" in v for v in violations_incorrect)


def test_empty_verified_and_missing_intervals():
    """Verify deterministic metrics behavior when verified or missing intervals are empty."""
    # 1. Both empty -> IoU is 1.0
    assert compute_interval_iou([], []) == 1.0

    # 2. One empty, one non-empty -> IoU is 0.0
    assert compute_interval_iou([], [(0, 50)]) == 0.0
    assert compute_interval_iou([(0, 50)], []) == 0.0

    # 3. Both zero volume -> volume ratio is 1.0
    assert compute_volume_ratio(0, 0) == 1.0
    # One zero, one positive -> volume ratio is 0.0
    assert compute_volume_ratio(0, 50) == 0.0
    assert compute_volume_ratio(50, 0) == 0.0


def test_invalid_coordinate_pair_rejection():
    """Verify that specifying start without end or end without start raises ValueError."""
    with pytest.raises(ValueError, match="Both evidence_start and evidence_end must be provided together"):
        ObservedRecoverySegment(
            segment_id="bad-pair-1",
            category="VERIFIED",
            evidence_start=10,
            evidence_end=None,  # MISSING END!
            original_start=0,
            original_end=10,
            recovered_start=0,
            recovered_end=10,
        )

    with pytest.raises(ValueError, match="Both original_start and original_end must be provided together"):
        ObservedRecoverySegment(
            segment_id="bad-pair-2",
            category="VERIFIED",
            evidence_start=0,
            evidence_end=10,
            original_start=None,  # MISSING START!
            original_end=10,
            recovered_start=0,
            recovered_end=10,
        )


def test_directional_relationship_mismatch():
    """Verify that inverted directed relationships report 0.0 accuracy."""
    gt_rel = [
        PhysicalRelationshipRecord(
            evidence_buffer_id="buf-1",
            source_artifact_id="art-A",
            target_artifact_id="art-B",
            relationship_type="CONTAINS",
        )
    ]
    # Observed has inverted direction: A is CONTAINED_BY B
    obs_rel = [
        ObservedRelationshipRecord(
            evidence_buffer_id="buf-1",
            source_candidate_id="art-A",
            target_candidate_id="art-B",
            relationship_type="CONTAINED_BY",
        )
    ]
    assert compute_relationship_accuracy(gt_rel, obs_rel) == 0.0


