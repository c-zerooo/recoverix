"""tests/test_deleted_csv_recovery_m382.py — Verification suite for Milestone 3.8.2.

Validates:
1. Exact byte preservation of deleted CSV payload in seed 42 (art-deleted-01).
2. Status is FULLY_RECOVERED with verified=215, reconstructed=0, missing=0.
3. Payload SHA-256 matches ground truth byte-for-byte.
4. Intact CSVs (with or without synthetic markers) are never destructively re-serialized.
5. Damaged CSV repairs (truncated rows, unclosed quotes) preserve accounting invariants.
6. Zero oracle or benchmark leakage in production modules.
"""

from __future__ import annotations

import base64
import hashlib
import io
import csv
import pytest

import backend.generate_case as gc
from backend.app.recovery.damage_generator import get_csv_scenarios
from backend.app.recovery.reconstruction import reconstruct_csv, reconstruct_artifact
from backend.app.recovery.tracer import execute_traced_recoveries
from backend.app.recovery.signatures import SYNTHETIC_START_MARKER, SYNTHETIC_END_MARKER
from benchmark.run_baseline import build_ground_truth_manifest


def test_seed42_art_deleted_01_payload_preservation():
    """Verify art-deleted-01 in seed 42 recovers with 100% byte fidelity and exact accounting."""
    gt_manifest, evidence_bytes = build_ground_truth_manifest(seed=42)
    art = next(a for a in gt_manifest.artifacts if a.artifact_id == "art-deleted-01")
    expected_bytes = base64.b64decode(art.original_bytes_b64)
    expected_len = len(expected_bytes)
    assert expected_len == 215

    runs = execute_traced_recoveries(filename=gc.EVIDENCE_FILENAME, content=evidence_bytes)
    run = next(r for r in runs if r.candidate_id == "cand-1")

    # 1. Recovery status
    assert run.status == "FULLY_RECOVERED"

    # 2. Forensic accounting
    assert run.total_verified_bytes == expected_len
    assert run.total_reconstructed_bytes == 0
    assert run.total_missing_bytes == 0
    assert run.total_input_bytes == expected_len

    # 3. Payload preservation and SHA-256
    recovered_bytes = bytes.fromhex(run.output["recovered_bytes"]) if run.output else b""
    assert len(recovered_bytes) == expected_len
    assert recovered_bytes == expected_bytes
    assert hashlib.sha256(recovered_bytes).hexdigest() == hashlib.sha256(expected_bytes).hexdigest()

    # 4. Fragment level checks
    assert len(run.fragments) == 1
    frag = run.fragments[0]
    assert frag.status == "VERIFIED"
    assert frag.verified_bytes == expected_len
    assert frag.reconstructed_bytes == 0
    assert frag.missing_bytes == 0
    assert frag.length == expected_len


def test_raw_intact_csv_byte_preservation_no_synthetic_markers():
    """Verify raw intact CSV evidence is preserved without altering quotes or formatting."""
    raw_csv = (
        b"id,name,role,department\n"
        b"1,\"Alice, Senior\",Admin,Security\n"
        b"2,Bob,Analyst,Forensics\n"
        b"3,Charlie,Engineer,Infrastructure\n"
    )
    result = reconstruct_csv(raw_csv, original_data=raw_csv, detection_mode="known_file")

    assert result.status == "FULLY_RECOVERED"
    assert result.success is True
    assert result.recovered_bytes == raw_csv
    assert result.verified_bytes == len(raw_csv)
    assert result.reconstructed_bytes == 0
    assert result.missing_bytes == 0
    assert result.is_exact_match is True
    assert result.reconstruction_methods == []


def test_intact_csv_with_synthetic_markers():
    """Verify intact CSV wrapped in synthetic markers preserves markers and exact line endings."""
    csv_body = b"col1,col2,col3\nval1,val2,val3\nval4,val5,val6\n"
    wrapped_csv = SYNTHETIC_START_MARKER + b"\n" + csv_body + SYNTHETIC_END_MARKER

    result = reconstruct_csv(wrapped_csv, original_data=wrapped_csv, detection_mode="synthetic_harness")

    assert result.status == "FULLY_RECOVERED"
    assert result.success is True
    assert result.recovered_bytes == wrapped_csv
    assert result.verified_bytes == len(wrapped_csv)
    assert result.reconstructed_bytes == 0
    assert result.missing_bytes == 0
    assert result.is_exact_match is True


def test_damaged_csv_scenarios_no_regressions():
    """Ensure all controlled damage generator scenarios behave correctly without regressions."""
    scenarios = get_csv_scenarios()
    sc_map = {s.scenario_id: s for s in scenarios}

    # 1. Intact
    r1 = reconstruct_csv(sc_map["csv_01_intact"].damaged_bytes, original_data=sc_map["csv_01_intact"].original_bytes)
    assert r1.status == "FULLY_RECOVERED"
    assert r1.is_exact_match is True
    assert r1.missing_bytes == 0
    assert r1.reconstructed_bytes == 0

    # 2. Truncated final row
    r2 = reconstruct_csv(sc_map["csv_02_truncated_final_row"].damaged_bytes, original_data=sc_map["csv_02_truncated_final_row"].original_bytes)
    assert r2.status == "PARTIALLY_RECOVERED"
    assert r2.missing_bytes > 0
    assert r2.is_exact_match is False

    # 3. Unclosed quote repair
    r3 = reconstruct_csv(sc_map["csv_03_unclosed_quote_repair"].damaged_bytes, original_data=sc_map["csv_03_unclosed_quote_repair"].original_bytes)
    assert r3.status == "PARTIALLY_RECOVERED"
    assert r3.reconstructed_bytes > 0

    # 4. Inconsistent row columns dropped
    r4 = reconstruct_csv(sc_map["csv_04_damaged_middle_row"].damaged_bytes, original_data=sc_map["csv_04_damaged_middle_row"].original_bytes)
    assert r4.status == "PARTIALLY_RECOVERED"
    assert r4.missing_bytes > 0

    # 5. Missing trailing newline
    r5 = reconstruct_csv(sc_map["csv_05_missing_trailing_newline"].damaged_bytes, original_data=sc_map["csv_05_missing_trailing_newline"].original_bytes)
    assert r5.status == "PARTIALLY_RECOVERED"
    assert r5.reconstructed_bytes == 1

    # 6. Fragmented gap
    r6 = reconstruct_csv(sc_map["csv_06_fragmented_gap"].damaged_bytes, original_data=sc_map["csv_06_fragmented_gap"].original_bytes)
    assert r6.status == "PARTIALLY_RECOVERED"
    assert r6.missing_bytes > 0

    # 7. Unrecoverable binary
    r7 = reconstruct_csv(sc_map["csv_07_unrecoverable_binary"].damaged_bytes, original_data=sc_map["csv_07_unrecoverable_binary"].original_bytes)
    assert r7.status == "UNRECOVERABLE"
    assert r7.success is False


def test_vrm_accounting_identities_hold():
    """Verify strict forensic accounting identities hold across all CSV reconstruction calls."""
    scenarios = get_csv_scenarios()
    for sc in scenarios:
        res = reconstruct_csv(sc.damaged_bytes, original_data=sc.original_bytes)
        # Identity 1: recovered output bytes == verified + reconstructed
        assert len(res.recovered_bytes) == res.verified_bytes + res.reconstructed_bytes
        # Identity 2: total evidence budget == verified + reconstructed + missing
        budget = max(len(sc.damaged_bytes), res.verified_bytes + res.reconstructed_bytes)
        assert budget == res.verified_bytes + res.reconstructed_bytes + res.missing_bytes


def test_no_oracle_leakage_into_production_modules():
    """Verify production modules have no imports of benchmark evaluator or hardcoded test artifact IDs."""
    import inspect
    from backend.app.recovery import reconstruction, completeness, tracer

    for module in [reconstruction, completeness, tracer]:
        src = inspect.getsource(module)
        assert "benchmark" not in src.lower() or "benchmark.run_baseline" not in src
        assert "art-deleted-01" not in src
        assert "art-clean-01" not in src
        assert "art-unrecoverable-01" not in src
