"""benchmark/expectations.py — Decoupled Forensic Expectation Oracle.

Derives deterministic forensic expectations (V/R/M byte budgets and expected status)
from physical ground-truth manifests without accessing recovery code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal, Tuple
from benchmark.models import PhysicalArtifactRecord, PhysicalDamageInterval


ExpectedStatus = Literal[
    "FULLY_RECOVERED",
    "PARTIALLY_RECOVERED",
    "CORRUPTED",
    "UNRECOVERABLE",
]


@dataclass(frozen=True)
class DerivedExpectation:
    """Forensic expectations deterministically derived from physical ground truth."""

    artifact_id: str
    expected_status: ExpectedStatus
    expected_verified_bytes: int
    expected_reconstructed_bytes: int
    expected_missing_bytes: int

    # Expected intervals in original artifact coordinates [start, end)
    expected_surviving_intervals: List[Tuple[int, int]] = field(default_factory=list)
    expected_missing_intervals: List[Tuple[int, int]] = field(default_factory=list)
    expected_reconstructed_intervals: List[Tuple[int, int]] = field(default_factory=list)
    expected_corrupted_intervals: List[Tuple[int, int]] = field(default_factory=list)

    forensic_classification_rule: str = ""


def derive_expected_recovery(artifact: PhysicalArtifactRecord) -> DerivedExpectation:
    """Derive deterministic recovery budgets and expected status from physical ground truth.

    Implements the approved deterministic status truth table:
      1. INTACT                  -> FULLY_RECOVERED
      2. PHYSICAL_GAP_UNREPAIRED -> PARTIALLY_RECOVERED
      3. DETERMINISTIC_REPAIR    -> PARTIALLY_RECOVERED
      4. UNREPAIRABLE_CORRUPTION -> CORRUPTED
      5. UNRECOVERABLE           -> UNRECOVERABLE

    Invariant: If R > 0 or M > 0, expected_status CANNOT be FULLY_RECOVERED.
    """
    orig_size = artifact.original_size_bytes

    # 1. Check explicit ground-truth unrecoverable scenario archetype
    if artifact.is_unrecoverable:
        return DerivedExpectation(
            artifact_id=artifact.artifact_id,
            expected_status="UNRECOVERABLE",
            expected_verified_bytes=0,
            expected_reconstructed_bytes=0,
            expected_missing_bytes=orig_size,
            expected_surviving_intervals=[],
            expected_missing_intervals=[(0, orig_size)],
            expected_reconstructed_intervals=[],
            expected_corrupted_intervals=[],
            forensic_classification_rule="UNRECOVERABLE_ARCHETYPE",
        )

    # 2. Partition damage intervals by physical nature and reconstruction mode
    missing_intervals: List[Tuple[int, int]] = []
    reconstructed_intervals: List[Tuple[int, int]] = []
    corrupted_intervals: List[Tuple[int, int]] = []

    has_gap_unrepaired = False
    has_deterministic_repair = False
    has_unrepairable_corruption = False

    for d in artifact.damage_intervals:
        span = (d.original_start, d.original_end)
        if d.reconstruction_mode == "RECONSTRUCTION_DETERMINISTIC":
            reconstructed_intervals.append(span)
            has_deterministic_repair = True
        elif d.damage_type == "PHYSICAL_GAP":
            missing_intervals.append(span)
            has_gap_unrepaired = True
        elif d.damage_type in ("ZERO_FILL", "RANDOM_OVERWRITE", "BIT_FLIP"):
            corrupted_intervals.append(span)
            has_unrepairable_corruption = True
        else:
            missing_intervals.append(span)

    # 3. Calculate surviving (verified) intervals from placements excluding damage
    # Placements define which slices are present in evidence
    surviving_intervals: List[Tuple[int, int]] = []
    damage_spans = set(missing_intervals + corrupted_intervals + reconstructed_intervals)

    for p in artifact.placements:
        p_start = p.original_offset
        p_end = p.original_offset + p.evidence_length

        # Check if placement overlaps any corruption or gap
        is_damaged = any(max(p_start, ds[0]) < min(p_end, ds[1]) for ds in damage_spans)
        if not is_damaged:
            surviving_intervals.append((p_start, p_end))

    total_missing = sum(end - start for start, end in missing_intervals)
    total_reconstructed = sum(end - start for start, end in reconstructed_intervals)
    total_corrupted = sum(end - start for start, end in corrupted_intervals)
    total_verified = sum(end - start for start, end in surviving_intervals)

    # 4. Apply Mutually Exclusive Status Truth Table
    if not artifact.damage_intervals:
        # Rule 1: INTACT
        status: ExpectedStatus = "FULLY_RECOVERED"
        rule_name = "INTACT"
        total_verified = orig_size
        total_reconstructed = 0
        total_missing = 0
        surviving_intervals = [(0, orig_size)]
    elif has_deterministic_repair:
        # Rule 3: DETERMINISTIC_REPAIR (R > 0 means status is PARTIALLY_RECOVERED, never FULLY)
        status = "PARTIALLY_RECOVERED"
        rule_name = "DETERMINISTIC_REPAIR"
    elif has_gap_unrepaired:
        # Rule 2: PHYSICAL_GAP_UNREPAIRED
        status = "PARTIALLY_RECOVERED"
        rule_name = "PHYSICAL_GAP_UNREPAIRED"
    elif has_unrepairable_corruption:
        # Rule 4: UNREPAIRABLE_CORRUPTION
        status = "CORRUPTED"
        rule_name = "UNREPAIRABLE_CORRUPTION"
    else:
        status = "PARTIALLY_RECOVERED"
        rule_name = "DEFAULT_PARTIAL"

    # Enforce invariant: R > 0 or M > 0 => cannot be FULLY_RECOVERED
    if (total_reconstructed > 0 or total_missing > 0) and status == "FULLY_RECOVERED":
        raise AssertionError("Derived expectation invariant violated: FULLY_RECOVERED with R > 0 or M > 0")

    return DerivedExpectation(
        artifact_id=artifact.artifact_id,
        expected_status=status,
        expected_verified_bytes=total_verified,
        expected_reconstructed_bytes=total_reconstructed,
        expected_missing_bytes=total_missing,
        expected_surviving_intervals=surviving_intervals,
        expected_missing_intervals=missing_intervals,
        expected_reconstructed_intervals=reconstructed_intervals,
        expected_corrupted_intervals=corrupted_intervals,
        forensic_classification_rule=rule_name,
    )
