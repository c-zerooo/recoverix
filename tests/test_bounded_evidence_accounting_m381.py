"""Milestone 3.8.1 — Bounded Evidence Accounting & False-Verification Fix Tests.

Validates that:
1. When candidate boundaries are unestablished or open-ended, the recovery run
   never claims the entire remainder of the evidence buffer as verified bytes.
2. An unrecoverable artifact candidate is declared UNRECOVERABLE with bounded
   verified accounting (0 verified bytes), eliminating OVERSTATED_VERIFICATION.
3. Clean and intact artifacts maintain exact verified accounting and FULLY_RECOVERED.
4. Candidate accounting identity holds: verified + reconstructed + missing == total_input.
5. In multi-candidate buffers, candidates are bounded by the next candidate offset.
6. The seed 42 benchmark scenario 'art-unrecoverable-01' produces 0 forensic violations.
7. No ground truth or benchmark structures leak into production recovery pipeline code.
"""

from typing import List
import pytest

from backend.app.recovery.scanner import Candidate
from backend.app.models.recovery_run import RecoveryRun
from backend.app.recovery.tracer import (
    CandidateEvidenceSpan,
    execute_traced_recoveries,
    resolve_candidate_evidence_span,
)
from benchmark.evaluator import evaluate_scenario
from benchmark.run_baseline import (
    build_ground_truth_manifest,
    run_baseline_benchmark,
    run_pipeline_and_observe,
)


def test_span_resolution_unbounded_candidate():
    """An unbounded candidate without next_offset is bounded by evidence length for searching,
    but defaults verified length to 0 when unestablished.
    """
    buffer_len = 524288
    cand = Candidate(
        candidate_id="cand-0",
        format="txt",
        mime_type="text/plain",
        category="text",
        offset=491520,
        detected_header_length=4,
        estimated_end_offset=None,
        detection_method="magic_bytes",
    )
    span = resolve_candidate_evidence_span(buffer_len, cand, next_offset=None)

    assert span.is_bounded is False
    assert span.evidence_start == 491520
    assert span.evidence_end is None
    assert span.search_limit == 524288

    # Fragments should not claim 32768 as verified before validation
    frag_len, frag_end = span.compute_fragment_bounds(verified_bytes=0)
    assert frag_len == 0
    assert frag_end == 491520

    # If 49 bytes are verified, bounds clamp to 49
    frag_len, frag_end = span.compute_fragment_bounds(verified_bytes=49)
    assert frag_len == 49
    assert frag_end == 491520 + 49
    assert span.bound_verified_bytes(524288) == 32768  # clamped to search limit


def test_span_resolution_bounded_candidate():
    """A bounded candidate with explicit estimated_end_offset preserves its span."""
    buffer_len = 100000
    cand = Candidate(
        candidate_id="cand-bounded",
        format="json",
        mime_type="application/json",
        category="structured",
        offset=1000,
        detected_header_length=1,
        estimated_end_offset=1500,
        detection_method="json_structure",
    )
    span = resolve_candidate_evidence_span(buffer_len, cand, next_offset=None)

    assert span.is_bounded is True
    assert span.evidence_start == 1000
    assert span.evidence_end == 1500
    assert span.search_limit == 1500

    frag_len, frag_end = span.compute_fragment_bounds(verified_bytes=500)
    assert frag_len == 500
    assert frag_end == 1500
    assert span.bound_verified_bytes(600) == 500  # clamped to bounded end


def test_span_resolution_clamped_by_next_candidate():
    """When a subsequent candidate begins before estimated_end, next_offset clamps search limit."""
    buffer_len = 100000
    cand = Candidate(
        candidate_id="cand-1",
        format="txt",
        mime_type="text/plain",
        category="text",
        offset=2000,
        detected_header_length=4,
        estimated_end_offset=None,
        detection_method="magic_bytes",
    )
    span = resolve_candidate_evidence_span(buffer_len, cand, next_offset=4000)

    assert span.search_limit == 4000
    assert span.is_bounded is False


def test_unrecoverable_artifact_in_large_buffer_never_overstates_verification():
    """Executing recovery on an unrecoverable artifact at offset 491520 in a 512KB buffer
    must NOT declare 32768 bytes verified.
    """
    buffer_size = 524288
    # 49 bytes of broken text header followed by 0xFF destroyed bytes
    evidence = bytearray(b"\x00" * buffer_size)
    cand_offset = 491520
    broken_payload = b"type: key_material\nalgorithm: AES-256-GCM\nkey_id: " + (b"\xff" * 200)
    evidence[cand_offset : cand_offset + len(broken_payload)] = broken_payload

    cand = Candidate(
        candidate_id="cand-unrec",
        format="txt",
        mime_type="text/plain",
        category="text",
        offset=cand_offset,
        detected_header_length=4,
        estimated_end_offset=None,
        detection_method="magic_bytes",
    )

    runs: List[RecoveryRun] = execute_traced_recoveries(
        candidates=[cand],
        content=bytes(evidence),
        filename="evidence.bin",
    )

    assert len(runs) == 1
    run = runs[0]

    # Must be UNRECOVERABLE, NOT CORRUPTED with full-buffer verified bytes
    assert run.status == "UNRECOVERABLE"
    assert run.total_verified_bytes == 0
    assert run.total_reconstructed_bytes == 0
    assert run.total_missing_bytes > 0
    # Accounting invariant holds
    assert run.total_verified_bytes + run.total_reconstructed_bytes + run.total_missing_bytes == run.total_input_bytes

    # Fragment-level accounting check
    assert len(run.fragments) == 1
    frag0 = run.fragments[0]
    assert frag0.verified_bytes == 0
    assert frag0.status == "UNRECOVERABLE"
    assert frag0.length == 0
    assert frag0.end_offset == cand_offset


def test_clean_intact_artifact_remains_fully_recovered():
    """An intact clean artifact must remain FULLY_RECOVERED with exact verified accounting."""
    clean_text = b"type: server_config\nhostname: prod-db-01\nport: 5432\nssl_mode: verify-full\n"
    buffer_size = 65536
    evidence = bytearray(b"\x00" * buffer_size)
    evidence[1024 : 1024 + len(clean_text)] = clean_text

    cand = Candidate(
        candidate_id="cand-clean",
        format="txt",
        mime_type="text/plain",
        category="text",
        offset=1024,
        detected_header_length=4,
        estimated_end_offset=1024 + len(clean_text),
        detection_method="magic_bytes",
    )

    runs = execute_traced_recoveries(
        candidates=[cand],
        content=bytes(evidence),
        filename="clean.txt",
    )

    assert len(runs) == 1
    run = runs[0]

    assert run.status == "FULLY_RECOVERED"
    assert run.total_verified_bytes == len(clean_text)
    assert run.total_reconstructed_bytes == 0
    assert run.total_missing_bytes == 0
    assert run.total_input_bytes == len(clean_text)

    frag0 = run.fragments[0]
    assert frag0.verified_bytes == len(clean_text)
    assert frag0.reconstructed_bytes == 0
    assert frag0.missing_bytes == 0
    assert frag0.status == "VERIFIED"


def test_art_unrecoverable_01_benchmark_scenario_no_violations():
    """Scenario art-unrecoverable-01 from the seed 42 baseline must produce zero forensic violations."""
    gt_manifest, evidence_bytes = build_ground_truth_manifest(seed=42)
    obs_manifest = run_pipeline_and_observe(gt_manifest.evidence_buffer_id, evidence_bytes)

    eval_report = evaluate_scenario(gt_manifest, obs_manifest)

    # Find evaluation for art-unrecoverable-01
    unrec_eval = next((ae for ae in eval_report.artifact_evaluations if ae.artifact_id == "art-unrecoverable-01"), None)
    assert unrec_eval is not None

    # Status must match UNRECOVERABLE
    assert unrec_eval.expected_status == "UNRECOVERABLE"
    assert unrec_eval.observed_status == "UNRECOVERABLE"
    assert unrec_eval.status_match is True
    assert unrec_eval.false_fully_recovered is False

    # Volume accounting
    assert unrec_eval.v_volume_accuracy == 1.0  # 0 verified vs 0 expected verified = 1.0

    # No OVERSTATED_VERIFICATION or other violations on this artifact
    violations = [v for v in eval_report.forensic_violations if "art-unrecoverable-01" in v or "OVERSTATED_VERIFICATION" in v]
    assert len(violations) == 0


def test_production_tracer_does_not_import_benchmark():
    """Verify that backend production recovery code has zero imports from benchmark."""
    import inspect
    import backend.app.recovery.tracer as tracer_module

    source = inspect.getsource(tracer_module)
    assert "import benchmark" not in source
    assert "from benchmark" not in source
    assert "PhysicalArtifactRecord" not in source
    assert "BenchmarkGroundTruthManifest" not in source
