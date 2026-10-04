"""
test_fragmented_txt_recovery_m383.py — Verification for Milestone 3.8.3.

Verifies marker-free physical/structural text extent stitching:
  1. Exact byte recovery and SHA-256 match for art-fragmented-01 in seed 42.
  2. Benchmark evaluator observes FULLY_RECOVERED with 0 forensic violations.
  3. Non-synthetic real-world fragmented text recovery (no synthetic markers).
  4. Non-zero entropy/noise in gap rejects stitching.
  5. Gap < 64 bytes rejects stitching (treated as intra-payload damage).
  6. Leading or trailing boundary misalignment rejects stitching.
  7. Invalid UTF-8 bytes in extent reject stitching.
  8. Single-extent text is not handled by stitching (requires >= 2 extents).
  9. Negative controls: bifragment (art-bifragment-01) and corrupted (art-corrupted-01) remain untouched.
  10. Strict forensic accounting: V = len(payload), R = 0, M = 0 with zero oracle leakage.
"""

from __future__ import annotations

import base64
import hashlib
from typing import List

import pytest

from backend.app.recovery.reconstruction import reconstruct_text, _try_stitch_fragmented_txt
from backend.app.recovery.tracer import execute_traced_recoveries
from benchmark.run_baseline import build_ground_truth_manifest, run_pipeline_and_observe
from benchmark.evaluator import evaluate_scenario


def test_01_art_fragmented_01_seed_42_end_to_end():
    """Verify that art-fragmented-01 recovers with 100% byte fidelity in seed 42."""
    gt_manifest, evidence_bytes = build_ground_truth_manifest(seed=42)
    art = next(a for a in gt_manifest.artifacts if a.artifact_id == "art-fragmented-01")
    expected_bytes = base64.b64decode(art.original_bytes_b64)
    expected_sha256 = hashlib.sha256(expected_bytes).hexdigest()

    runs = execute_traced_recoveries("damaged.img", evidence_bytes)
    cand2_run = next(r for r in runs if getattr(r, "candidate_id", None) == "cand-2")

    # 1. Recovery status and byte counts
    assert cand2_run.status == "FULLY_RECOVERED"
    assert cand2_run.total_verified_bytes == 393
    assert cand2_run.total_reconstructed_bytes == 0
    assert cand2_run.total_missing_bytes == 0
    assert cand2_run.total_input_bytes == 393

    # 2. Payload exact match
    payload = bytes.fromhex(cand2_run.output["recovered_bytes"])
    assert len(payload) == 393
    assert payload == expected_bytes
    assert hashlib.sha256(payload).hexdigest() == expected_sha256

    # 3. Exactly 3 physical fragments observed matching disk extents
    assert len(cand2_run.fragments) == 3
    expected_extents = [
        (131072, 131),
        (196608, 131),
        (262144, 131),
    ]
    for idx, (exp_off, exp_len) in enumerate(expected_extents):
        frag = cand2_run.fragments[idx]
        assert frag.fragment_id == f"frag-{idx}"
        assert frag.offset == exp_off
        assert frag.length == exp_len
        assert frag.end_offset == exp_off + exp_len
        assert frag.verified_bytes == exp_len
        assert frag.reconstructed_bytes == 0
        assert frag.missing_bytes == 0
        assert frag.status == "VERIFIED"


def test_02_benchmark_evaluator_observes_art_fragmented_01():
    """Verify that benchmark evaluator reports passing for art-fragmented-01."""
    gt_manifest, evidence_bytes = build_ground_truth_manifest(seed=42)
    obs_manifest = run_pipeline_and_observe("damaged.img", evidence_bytes)
    report = evaluate_scenario(gt_manifest, obs_manifest)

    frag_eval = next(ae for ae in report.artifact_evaluations if ae.artifact_id == "art-fragmented-01")
    assert frag_eval.expected_status == "FULLY_RECOVERED"
    assert frag_eval.observed_status == "FULLY_RECOVERED"
    assert frag_eval.status_match is True
    assert frag_eval.v_volume_accuracy == 1.0
    assert frag_eval.r_volume_accuracy == 1.0
    assert frag_eval.m_volume_accuracy == 1.0
    assert frag_eval.whole_payload_hash_match is True
    assert frag_eval.false_fully_recovered is False

    # Forensic violations must remain zero across entire benchmark
    assert len(report.forensic_violations) == 0


def test_03_non_synthetic_fragmented_txt():
    """Verify marker-free real-world fragmented text stitching across zero-fill gaps."""
    doc = (
        b"# Operational Incident Log\n\n"
        b"Severity: HIGH\n"
        b"Host: prd-app-server-04\n\n"
        b"Details:\n"
        b"Disk controller reported read timeouts at 01:23:45 UTC.\n"
        b"Automatic failover completed to secondary node at 01:24:12 UTC.\n"
        b"No data loss reported in primary database.\n\n"
        b"Status: CLOSED\n"
    )
    # Split into 3 extents across 4096-byte cluster boundaries
    e0 = doc[:80]
    e1 = doc[80:200]
    e2 = doc[200:]
    cluster_gap = b"\x00" * 4096

    evidence_window = e0 + cluster_gap + e1 + cluster_gap + e2

    res = _try_stitch_fragmented_txt(evidence_window, source_offset=1000)
    assert res is not None
    stitched, frags, val_res = res
    assert stitched == doc
    assert val_res.valid is True
    assert len(frags) == 3
    assert frags[0] == (1000, len(e0))
    assert frags[1] == (1000 + len(e0) + 4096, len(e1))
    assert frags[2] == (1000 + len(e0) + 4096 + len(e1) + 4096, len(e2))


def test_04_non_zero_gap_rejects_stitching():
    """If an intermediate gap contains non-zero noise/entropy, reject stitching."""
    e0 = b"First line of log.\n"
    e1 = b"Second line of log.\n"
    gap_with_noise = b"\x00" * 100 + b"\xff\xfe\xca\xfe" + b"\x00" * 100
    evidence = e0 + gap_with_noise + e1

    assert _try_stitch_fragmented_txt(evidence, source_offset=0) is None


def test_05_gap_less_than_64_bytes_rejects_stitching():
    """Gaps smaller than 64 bytes are treated as intra-file null loss, not storage extents."""
    e0 = b"Header block of record.\n"
    e1 = b"Footer block of record.\n"
    small_gap = b"\x00" * 48  # < 64 bytes
    evidence = e0 + small_gap + e1

    assert _try_stitch_fragmented_txt(evidence, source_offset=0, min_gap_size=64) is None


def test_06_leading_trailing_boundary_misalignment_rejects_stitching():
    """Leading or trailing zeros outside extents indicate candidate boundary misalignment."""
    e0 = b"Extent alpha.\n"
    e1 = b"Extent beta.\n"
    gap = b"\x00" * 128

    # Leading zeros before Extent 0
    leading_bad = (b"\x00" * 16) + e0 + gap + e1
    assert _try_stitch_fragmented_txt(leading_bad, source_offset=0) is None

    # Trailing zeros after Extent 1
    trailing_bad = e0 + gap + e1 + (b"\x00" * 16)
    assert _try_stitch_fragmented_txt(trailing_bad, source_offset=0) is None


def test_07_invalid_utf8_extent_rejects_stitching():
    """If any extent contains invalid UTF-8 bytes, stitching must fail."""
    e0 = b"Valid text header.\n"
    e1 = b"\x80\x81\x82\x83\xff\xfe invalid binary"
    gap = b"\x00" * 128
    evidence = e0 + gap + e1

    assert _try_stitch_fragmented_txt(evidence, source_offset=0) is None


def test_08_single_extent_not_handled_by_stitching():
    """Contiguous single-extent text must not be handled by multi-extent stitching."""
    evidence = b"Single contiguous text document with no gaps.\n"
    assert _try_stitch_fragmented_txt(evidence, source_offset=0) is None


def test_09_bifragment_and_corrupted_remain_untouched():
    """Verify that art-bifragment-01 and art-corrupted-01 are not modified by this fix."""
    gt_manifest, evidence_bytes = build_ground_truth_manifest(seed=42)
    obs_manifest = run_pipeline_and_observe("damaged.img", evidence_bytes)
    report = evaluate_scenario(gt_manifest, obs_manifest)

    bifrag_eval = next(ae for ae in report.artifact_evaluations if ae.artifact_id == "art-bifragment-01")
    # Bifragment remains unrecovered by production engine (gap contains random binary data)
    # Under 3.8.4 non-deterministic modeling, expected is UNRECOVERABLE and matches observed UNRECOVERABLE
    assert bifrag_eval.expected_status == "UNRECOVERABLE"
    assert bifrag_eval.observed_status == "UNRECOVERABLE"
    assert bifrag_eval.status_match is True
    assert bifrag_eval.false_fully_recovered is False

    corr_eval = next(ae for ae in report.artifact_evaluations if ae.artifact_id == "art-corrupted-01")
    # Under 3.8.5, corrupted TXT classification is fixed: expected is CORRUPTED and matches observed CORRUPTED
    assert corr_eval.expected_status == "CORRUPTED"
    assert corr_eval.observed_status == "CORRUPTED"
    assert corr_eval.status_match is True


def test_10_zero_oracle_leakage_and_vrm_accounting():
    """Verify reconstruct_text operates purely on evidence with strict V/R/M accounting."""
    frag0 = b"field_a: 1\n"
    frag1 = b"field_b: 2\n"
    frag2 = b"field_c: 3\n"
    gap = b"\x00" * 512
    raw_evidence = frag0 + gap + frag1 + gap + frag2

    # original_data=None explicitly passed — zero oracle information
    res = reconstruct_text(raw_evidence, original_data=None, source_offset=2048)
    assert res.status == "FULLY_RECOVERED"
    assert res.success is True
    expected_v = len(frag0) + len(frag1) + len(frag2)
    assert res.verified_bytes == expected_v
    assert res.reconstructed_bytes == 0
    assert res.missing_bytes == 0
    assert res.is_exact_match is None
    assert res.details["reconstruction_method"] == "FRAGMENTED_EXTENT_STITCHING"
    assert len(res.details["physical_fragments"]) == 3
    assert res.details["unallocated_gap_bytes"] == len(raw_evidence) - expected_v
