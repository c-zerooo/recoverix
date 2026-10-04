"""
test_corrupted_txt_recovery_m385.py — Verification suite for Milestone 3.8.5.

Verifies deterministic classification of corrupted text evidence:
1. Seed-42 corrupted TXT (art-corrupted-01) becomes CORRUPTED.
2. Corrupted TXT has verified_bytes == 0, reconstructed_bytes == 0, missing_bytes == total_input_bytes.
3. Corrupted TXT does not emit fabricated '?' or ' ' replacement bytes as reconstructed payload.
4. Clean TXT (art-clean-01) remains FULLY_RECOVERED.
5. Fragmented TXT (art-fragmented-01) remains FULLY_RECOVERED.
6. Bifragment TXT (art-bifragment-01) remains UNRECOVERABLE (not misclassified as CORRUPTED).
7. Unrecoverable TXT (art-unrecoverable-01) remains UNRECOVERABLE (not misclassified as CORRUPTED).
8. Zero oracle leakage: recovery runs purely on evidence bytes without ground truth.
9. V/R/M forensic accounting invariant holds across all scenarios.
10. The CORRUPTED status survives through canonical RecoveryRun and pipeline event trace.
11. Direct unit test of reconstruct_txt on bounded invalid UTF-8 evidence.
"""

from __future__ import annotations

import inspect
from pathlib import Path
import pytest

from backend.app.recovery.signatures import (
    SYNTHETIC_START_MARKER,
    SYNTHETIC_END_MARKER,
)
from backend.app.recovery.reconstructors.txt import reconstruct_txt
from backend.app.recovery.tracer import execute_traced_recoveries
from backend.app.models.reconstruction import ReconstructionResult
from backend.app.models.recovery_run import RecoveryRun
from benchmark.run_baseline import (
    build_ground_truth_manifest,
    run_baseline_benchmark,
    run_pipeline_and_observe,
)
from benchmark.evaluator import evaluate_scenario


def test_01_seed_42_corrupted_txt_becomes_corrupted():
    """1. Verify that art-corrupted-01 is classified as CORRUPTED and passes benchmark evaluation."""
    report = run_baseline_benchmark(seed=42, verbose=False)
    corr_sc = next(s for s in report["scenarios"] if s["artifact_id"] == "art-corrupted-01")

    assert corr_sc["passed"] is True
    assert corr_sc["status"]["expected"] == "CORRUPTED"
    assert corr_sc["status"]["observed"] == "CORRUPTED"
    assert corr_sc["status"]["match"] is True


def test_02_corrupted_txt_has_zero_verified_and_reconstructed_bytes():
    """2. Verify that corrupted TXT evidence has V=0 and R=0, avoiding false verification claims."""
    gt_manifest, evidence_bytes = build_ground_truth_manifest(seed=42)
    obs_manifest = run_pipeline_and_observe("damaged.img", evidence_bytes)

    # Locate art-corrupted-01
    art_corr = next(a for a in gt_manifest.artifacts if a.artifact_id == "art-corrupted-01")
    cand_corr = next(
        c for c in obs_manifest.candidates
        if c.offset == art_corr.placements[0].evidence_offset
    )
    rec_corr = next(
        r for r in obs_manifest.recoveries
        if r.observed_candidate_id == cand_corr.candidate_id
    )

    assert rec_corr.observed_status == "CORRUPTED"
    assert rec_corr.total_verified_bytes == 0
    assert rec_corr.total_reconstructed_bytes == 0
    assert rec_corr.total_missing_bytes == rec_corr.total_input_bytes
    assert len(rec_corr.verified_segments) == 0
    assert len(rec_corr.reconstructed_segments) == 0


def test_03_no_fabricated_replacement_bytes():
    """3. Verify that corrupted TXT does not emit fabricated '?' or ' ' as reconstructed payload."""
    gt_manifest, evidence_bytes = build_ground_truth_manifest(seed=42)
    art_corr = next(a for a in gt_manifest.artifacts if a.artifact_id == "art-corrupted-01")
    p = art_corr.placements[0]
    raw_carved = evidence_bytes[p.evidence_offset : p.evidence_offset + p.evidence_length]

    res = reconstruct_txt(raw_carved)

    assert res.status == "CORRUPTED"
    assert res.success is False
    assert res.verified_bytes == 0
    assert res.reconstructed_bytes == 0
    assert res.reconstruction_methods == []
    # Exact raw bytes preserved, not mutated with replacement chars
    assert res.recovered_bytes == raw_carved


def test_04_negative_control_clean_txt_remains_fully_recovered():
    """4. Negative control: art-clean-01 remains FULLY_RECOVERED."""
    report = run_baseline_benchmark(seed=42, verbose=False)
    clean_sc = next(s for s in report["scenarios"] if s["artifact_id"] == "art-clean-01")

    assert clean_sc["passed"] is True
    assert clean_sc["status"]["expected"] == "FULLY_RECOVERED"
    assert clean_sc["status"]["observed"] == "FULLY_RECOVERED"
    assert clean_sc["volumes"]["accuracy"]["verified"] == 1.0


def test_05_negative_control_fragmented_txt_remains_fully_recovered():
    """5. Negative control: art-fragmented-01 remains FULLY_RECOVERED across unallocated zero-fill gaps."""
    report = run_baseline_benchmark(seed=42, verbose=False)
    frag_sc = next(s for s in report["scenarios"] if s["artifact_id"] == "art-fragmented-01")

    assert frag_sc["passed"] is True
    assert frag_sc["status"]["expected"] == "FULLY_RECOVERED"
    assert frag_sc["status"]["observed"] == "FULLY_RECOVERED"
    assert frag_sc["whole_payload_hash_match"] is True


def test_06_negative_control_bifragment_remains_unrecoverable():
    """6. Negative control: art-bifragment-01 remains UNRECOVERABLE (not misclassified as CORRUPTED)."""
    report = run_baseline_benchmark(seed=42, verbose=False)
    bifrag_sc = next(s for s in report["scenarios"] if s["artifact_id"] == "art-bifragment-01")

    assert bifrag_sc["passed"] is True
    assert bifrag_sc["status"]["expected"] == "UNRECOVERABLE"
    assert bifrag_sc["status"]["observed"] == "UNRECOVERABLE"


def test_07_negative_control_unrecoverable_remains_unrecoverable():
    """7. Negative control: art-unrecoverable-01 remains UNRECOVERABLE (not misclassified as CORRUPTED)."""
    report = run_baseline_benchmark(seed=42, verbose=False)
    unrec_sc = next(s for s in report["scenarios"] if s["artifact_id"] == "art-unrecoverable-01")

    assert unrec_sc["passed"] is True
    assert unrec_sc["status"]["expected"] == "UNRECOVERABLE"
    assert unrec_sc["status"]["observed"] == "UNRECOVERABLE"
    assert unrec_sc["volumes"]["observed"]["verified"] == 0


def test_08_zero_oracle_leakage():
    """8. Verify that production recovery APIs accept zero ground-truth parameters."""
    sig_recon = inspect.signature(reconstruct_txt)
    # ground_truth parameter is optional and None by default
    assert sig_recon.parameters["ground_truth"].default is None

    # Test reconstruction with explicit None for ground_truth
    test_evidence = SYNTHETIC_START_MARKER + b"FMT:txt;Valid payload\n" + SYNTHETIC_END_MARKER
    res_none = reconstruct_txt(test_evidence, ground_truth=None)
    assert res_none.status == "FULLY_RECOVERED"

    # tracer.execute_traced_recoveries accepts only filename, content, detection_mode
    sig_tracer = inspect.signature(execute_traced_recoveries)
    param_names = list(sig_tracer.parameters.keys())
    assert "gt_manifest" not in param_names
    assert "ground_truth" not in param_names


def test_09_vrm_accounting_invariant_holds():
    """9. Verify V/R/M forensic accounting invariant holds across all benchmark scenarios."""
    report = run_baseline_benchmark(seed=42, verbose=False)
    for sc in report["scenarios"]:
        obs_v = sc["volumes"]["observed"]["verified"]
        obs_r = sc["volumes"]["observed"]["reconstructed"]
        obs_m = sc["volumes"]["observed"]["missing"]
        assert obs_v >= 0
        assert obs_r >= 0
        assert obs_m >= 0


def test_10_corrupted_status_survives_in_recovery_run():
    """10. Verify that RecoveryRun accurately records CORRUPTED status, fragment state, and events."""
    gt_manifest, evidence_bytes = build_ground_truth_manifest(seed=42)
    runs = execute_traced_recoveries(filename="damaged.img", content=evidence_bytes)

    art_corr = next(a for a in gt_manifest.artifacts if a.artifact_id == "art-corrupted-01")
    corr_offset = art_corr.placements[0].evidence_offset

    corr_run = next(r for r in runs if r.provenance.get("evidence_start") == corr_offset)

    assert corr_run.status == "CORRUPTED"
    assert corr_run.total_verified_bytes == 0
    assert corr_run.total_reconstructed_bytes == 0
    assert corr_run.total_missing_bytes == corr_run.total_input_bytes
    assert corr_run.fragments[0].status == "CORRUPTED"
    assert corr_run.fragments[0].verified_bytes == 0
    assert corr_run.fragments[0].validation_status == "FAILED"
    assert any(dmg.type == "CORRUPTED" for dmg in corr_run.damage_regions)


def test_11_unit_bounded_corrupted_txt_reconstruction():
    """11. Direct unit test of reconstruct_txt on synthesized bounded corrupted text."""
    prefix = SYNTHETIC_START_MARKER + b"FMT:txt;Header Info\n"
    corrupt_bytes = b"\x8f\xde\x9a\xfe\x00\x16\xff"  # Invalid UTF-8 noise
    suffix = b"\nFooter Info" + SYNTHETIC_END_MARKER
    evidence = prefix + corrupt_bytes + suffix

    res = reconstruct_txt(evidence)

    assert isinstance(res, ReconstructionResult)
    assert res.format == "txt"
    assert res.status == "CORRUPTED"
    assert res.success is False
    assert res.verified_bytes == 0
    assert res.reconstructed_bytes == 0
    assert res.missing_bytes == len(evidence)
    assert res.damage_regions[0]["type"] == "CORRUPTED"
    assert res.validation_result is not None
    assert res.validation_result.valid is False
