"""
test_reconstruction_txt_csv.py — Rigorous test suite for TXT & CSV deterministic reconstruction.

Validates the full reconstruction contract:
  original file
  → damaged file
  → Recoverix output
  → validation
  → SHA-256 comparison where applicable
  → verified bytes
  → structurally repaired bytes
  → missing bytes
"""

from __future__ import annotations

import hashlib
import io
import csv
import pytest

from backend.app.recovery.reconstruction import (
    reconstruct_text,
    reconstruct_csv,
    reconstruct_artifact,
)
from backend.app.recovery.damage_generator import (
    get_txt_scenarios,
    get_csv_scenarios,
    DamageScenario,
)
from backend.app.recovery.validators.text import validate_txt
from backend.app.recovery.validators.csv import validate_csv


def _log_forensic_trace(scenario: DamageScenario, result):
    """Print detailed forensic execution trace for the test run."""
    print(f"\n{'='*70}")
    print(f"SCENARIO: {scenario.scenario_id} ({scenario.format.upper()})")
    print(f"DESCRIPTION: {scenario.description}")
    print(f"{'-'*70}")
    print(f"ORIGINAL FILE: {len(scenario.original_bytes)} bytes | SHA256: {scenario.original_sha256[:16]}...")
    print(f"DAMAGED FILE:  {len(scenario.damaged_bytes)} bytes | SHA256: {scenario.damaged_sha256[:16]}... | Damage: {scenario.damage_type}")
    print(f"RECOVERIX STATUS: {result.status} | Success: {result.success}")
    print(f"OUTPUT SIZE:   {len(result.recovered_bytes)} bytes")
    print(f"BYTE ACCOUNTING: verified={result.verified_bytes}, reconstructed={result.reconstructed_bytes}, missing={result.missing_bytes}")
    print(f"VALIDATION:    valid={result.validation_result.valid if result.validation_result else False}, errors={result.validation_result.errors if result.validation_result else []}")
    print(f"METHODS:       {result.reconstruction_methods}")
    if result.is_exact_match is not None:
        print(f"EXACT SHA-256 MATCH: {result.is_exact_match}")
    print(f"{'='*70}\n")


# ── TXT Reconstruction Tests ────────────────────────────────────────────────

@pytest.mark.parametrize("scenario", get_txt_scenarios(), ids=lambda s: s.scenario_id)
def test_txt_reconstruction_scenarios(scenario: DamageScenario):
    """Test all TXT damage scenarios against the deterministic reconstruction engine."""
    result = reconstruct_text(scenario.damaged_bytes, original_data=scenario.original_bytes)
    _log_forensic_trace(scenario, result)

    assert result.format == "txt"
    assert result.success == scenario.expected_recoverability

    if scenario.expected_recoverability:
        # 1. Output must be structurally valid TXT
        assert result.validation_result is not None
        assert result.validation_result.valid is True
        assert len(result.validation_result.errors) == 0

        # 2. Output bytes must be non-empty
        assert len(result.recovered_bytes) > 0

        # 3. Exact Byte Accounting Invariant:
        # len(recovered_bytes) == verified_bytes + reconstructed_bytes
        assert len(result.recovered_bytes) == result.verified_bytes + result.reconstructed_bytes

        # 4. Independent validation of the output bytes
        independent_val = validate_txt(result.recovered_bytes)
        assert independent_val.valid is True

        # 5. Check exact match expectations
        if scenario.expected_exact_sha:
            assert result.is_exact_match is True
            assert hashlib.sha256(result.recovered_bytes).hexdigest() == scenario.original_sha256
            assert result.missing_bytes == 0
        else:
            assert result.is_exact_match is False
            assert result.missing_bytes > 0

        # 6. Status follows the forensic accounting invariant, never the
        #    byte-exactness of the output. A byte-exact output can still contain
        #    structurally reconstructed bytes, and anything reconstructed is not
        #    verified, so it must never be reported as FULLY_RECOVERED.
        if result.reconstructed_bytes > 0 or result.missing_bytes > 0:
            assert result.status == "PARTIALLY_RECOVERED"
        else:
            assert result.status == "FULLY_RECOVERED"
    else:
        # Unrecoverable scenario
        assert result.status == "UNRECOVERABLE"
        assert result.success is False
        assert result.verified_bytes == 0
        assert result.recovered_bytes == b""


# ── CSV Reconstruction Tests ────────────────────────────────────────────────

@pytest.mark.parametrize("scenario", get_csv_scenarios(), ids=lambda s: s.scenario_id)
def test_csv_reconstruction_scenarios(scenario: DamageScenario):
    """Test all CSV damage scenarios against the deterministic reconstruction engine."""
    result = reconstruct_csv(scenario.damaged_bytes, original_data=scenario.original_bytes)
    _log_forensic_trace(scenario, result)

    assert result.format == "csv"
    assert result.success == scenario.expected_recoverability

    if scenario.expected_recoverability:
        # 1. Output must be structurally valid CSV
        assert result.validation_result is not None
        assert result.validation_result.valid is True
        assert len(result.validation_result.errors) == 0

        # 2. Output bytes must be non-empty
        assert len(result.recovered_bytes) > 0

        # 3. Exact Byte Accounting Invariant:
        # len(recovered_bytes) == verified_bytes + reconstructed_bytes
        assert len(result.recovered_bytes) == result.verified_bytes + result.reconstructed_bytes

        # 4. Independent validation of the output bytes
        independent_val = validate_csv(result.recovered_bytes)
        assert independent_val.valid is True

        # 5. Verify row structural uniformity in the recovered file
        # Strip synthetic markers if present to parse CSV directly
        body = result.recovered_bytes
        if b"[SYNTHETIC_ARTIFACT_START]" in body:
            s_idx = body.find(b"[SYNTHETIC_ARTIFACT_START]") + len(b"[SYNTHETIC_ARTIFACT_START]")
            e_idx = body.find(b"[SYNTHETIC_ARTIFACT_END]")
            body = body[s_idx:e_idx]

        reader = csv.reader(io.StringIO(body.decode("utf-8")))
        rows = [r for r in reader if any(f.strip() for f in r)]
        assert len(rows) > 0
        col_counts = [len(r) for r in rows]
        assert len(set(col_counts)) == 1, f"Inconsistent row columns in output: {col_counts}"

        # 6. Check exact match expectations
        if scenario.expected_exact_sha:
            assert result.is_exact_match is True
            assert hashlib.sha256(result.recovered_bytes).hexdigest() == scenario.original_sha256
            assert result.missing_bytes == 0
        else:
            assert result.is_exact_match is False
            assert result.missing_bytes > 0

        # 7. Status follows the forensic accounting invariant, never the
        #    byte-exactness of the output. A byte-exact output can still contain
        #    structurally reconstructed bytes, and anything reconstructed is not
        #    verified, so it must never be reported as FULLY_RECOVERED.
        if result.reconstructed_bytes > 0 or result.missing_bytes > 0:
            assert result.status == "PARTIALLY_RECOVERED"
        else:
            assert result.status == "FULLY_RECOVERED"
    else:
        # Unrecoverable scenario
        assert result.status == "UNRECOVERABLE"
        assert result.success is False
        assert result.verified_bytes == 0
        assert result.recovered_bytes == b""


# ── Unified Dispatcher Tests ────────────────────────────────────────────────

def test_reconstruct_artifact_dispatch():
    """Verify reconstruct_artifact correctly routes TXT and CSV."""
    txt_content = b"Simple intact plain text."
    txt_res = reconstruct_artifact("txt", txt_content)
    assert txt_res.format == "txt"
    assert txt_res.success is True

    csv_content = b"col1,col2\nval1,val2\n"
    csv_res = reconstruct_artifact("csv", csv_content)
    assert csv_res.format == "csv"
    assert csv_res.success is True

    unknown_res = reconstruct_artifact("xyz_unknown", b"data")
    assert unknown_res.success is False
    assert unknown_res.status == "UNRECOVERABLE"
