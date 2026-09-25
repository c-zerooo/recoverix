"""
bifragment.py — Deterministic bounded bifragment reconstruction layer.

Attempt structural reconstruction of two recovered fragments (Fragment A and Fragment B)
separated by an unknown bounded gap of 1 to 4096 bytes.

FORENSIC PRINCIPLE:
  - Known bytes from Fragment A and Fragment B are NEVER modified.
  - Unknown bytes in the gap are NEVER invented, inferred, or synthesized as evidence.
  - Gap candidate byte sequences are constructed strictly in-memory to execute
    structural validation rules, establishing whether a valid structural relationship
    exists for a candidate gap size N.
  - The missing region is explicitly recorded as unobserved metadata.
"""

from __future__ import annotations

from typing import Callable, Union, Optional, Any

from backend.app.models.validation import ValidationResult
from backend.app.models.reconstruction import BifragmentReconstructionResult
from backend.app.recovery.carver import RecoveredArtifact
from backend.app.recovery.signatures import (
    SYNTHETIC_START_MARKER,
    SYNTHETIC_END_MARKER,
)


def reconstruct_bifragment(
    fragment_a: bytes | RecoveredArtifact,
    fragment_b: bytes | RecoveredArtifact,
    validator: Callable[[bytes], ValidationResult],
    min_gap: int = 1,
    max_gap: int = 4096,
    gap_placeholder: bytes = b" ",
) -> BifragmentReconstructionResult:
    """Attempt bounded bifragment reconstruction for two fragments across a gap.

    Search bounds are strictly limited to [min_gap, max_gap] (where 1 <= min_gap <= max_gap <= 4096).
    Candidate gap sizes are tested using *validator*. If one or more gap sizes produce
    a valid ValidationResult, the smallest valid gap size is selected.

    Args:
        fragment_a: First fragment (raw bytes or RecoveredArtifact).
        fragment_b: Second fragment (raw bytes or RecoveredArtifact).
        validator: Structural validation function accepting bytes.
        min_gap: Minimum gap size to test (default 1, minimum 1).
        max_gap: Maximum gap size to test (default 4096, maximum 4096).
        gap_placeholder: Byte sequence used during validator evaluation (default b" ").
            These bytes are used strictly for format/marker parsing and are NEVER
            presented as recovered evidence.

    Returns:
        A BifragmentReconstructionResult recording the outcome, selected gap size,
        validation result, candidate count, and forensic missing-region metadata.

    Raises:
        ValueError: If min_gap < 1, max_gap > 4096, min_gap > max_gap, empty fragments,
            or invalid fragment ordering (e.g. end marker before start marker).
        TypeError: If fragment inputs or validator are invalid types.
    """
    # 1. Validate search range bounds
    if min_gap < 1:
        raise ValueError(f"min_gap must be >= 1, got {min_gap}")
    if max_gap > 4096:
        raise ValueError(f"max_gap must be <= 4096, got {max_gap}")
    if min_gap > max_gap:
        raise ValueError(f"min_gap ({min_gap}) cannot be greater than max_gap ({max_gap})")

    # 2. Extract fragment bytes, IDs, and format
    raw_a: bytes
    id_a: str = "frag_a"
    fmt_a: str = "txt"
    if isinstance(fragment_a, RecoveredArtifact):
        raw_a = bytes(fragment_a.recovered_bytes)
        id_a = fragment_a.candidate_id
        if fragment_a.format:
            fmt_a = fragment_a.format
    elif isinstance(fragment_a, (bytes, bytearray)):
        raw_a = bytes(fragment_a)
    else:
        raise TypeError(f"Invalid type for fragment_a: {type(fragment_a)}. Expected bytes or RecoveredArtifact.")

    raw_b: bytes
    id_b: str = "frag_b"
    fmt_b: str = "txt"
    if isinstance(fragment_b, RecoveredArtifact):
        raw_b = bytes(fragment_b.recovered_bytes)
        id_b = fragment_b.candidate_id
        if fragment_b.format:
            fmt_b = fragment_b.format
    elif isinstance(fragment_b, (bytes, bytearray)):
        raw_b = bytes(fragment_b)
    else:
        raise TypeError(f"Invalid type for fragment_b: {type(fragment_b)}. Expected bytes or RecoveredArtifact.")

    # 3. Check non-empty fragments
    if len(raw_a) == 0:
        raise ValueError("fragment_a bytes cannot be empty")
    if len(raw_b) == 0:
        raise ValueError("fragment_b bytes cannot be empty")

    if not callable(validator):
        raise TypeError(f"validator must be a callable function, got {type(validator)}")

    fmt = fmt_a if fmt_a == fmt_b else "txt"

    # 4. Fragment ordering check (for synthetic boundary markers)
    has_end_a = SYNTHETIC_END_MARKER in raw_a
    has_start_b = SYNTHETIC_START_MARKER in raw_b

    if has_end_a and has_start_b:
        raise ValueError(
            "Invalid fragment ordering: fragment_a contains end marker and fragment_b contains start marker."
        )

    # 5. Search for valid gap candidates strictly in [min_gap, max_gap]
    valid_candidates: list[tuple[int, ValidationResult]] = []

    for gap_size in range(min_gap, max_gap + 1):
        # Construct temporary validation candidate
        test_payload = raw_a + (gap_placeholder * gap_size) + raw_b
        try:
            val_res = validator(test_payload)
            if isinstance(val_res, ValidationResult) and val_res.valid:
                valid_candidates.append((gap_size, val_res))
        except Exception:
            # Defensive: validator errors on a single candidate gap should not crash reconstruction.
            continue

    # 6. Select outcome
    valid_count = len(valid_candidates)

    if valid_count > 0:
        # Select SMALLEST valid gap size
        valid_candidates.sort(key=lambda item: item[0])
        smallest_gap, best_validation = valid_candidates[0]

        return BifragmentReconstructionResult(
            success=True,
            format=fmt,
            fragment_a_id=id_a,
            fragment_b_id=id_b,
            gap_size=smallest_gap,
            missing_byte_count=smallest_gap,
            reconstruction_method="BOUNDED_BIFRAGMENT",
            validation_result=best_validation,
            valid_candidate_count=valid_count,
            fragment_a_bytes=raw_a,
            fragment_b_bytes=raw_b,
            missing_region_metadata={
                "status": "BOUNDED_GAP_VERIFIED",
                "missing_byte_count": smallest_gap,
                "gap_range_searched": [min_gap, max_gap],
                "valid_candidate_count": valid_count,
                "unknown_bytes_notice": (
                    f"Structural validation succeeded with gap size {smallest_gap}. "
                    "The missing bytes themselves are unobserved and NOT synthesized."
                ),
            },
        )
    else:
        return BifragmentReconstructionResult(
            success=False,
            format=fmt,
            fragment_a_id=id_a,
            fragment_b_id=id_b,
            gap_size=None,
            missing_byte_count=0,
            reconstruction_method="BOUNDED_BIFRAGMENT",
            validation_result=None,
            valid_candidate_count=0,
            fragment_a_bytes=raw_a,
            fragment_b_bytes=raw_b,
            missing_region_metadata={
                "status": "RECONSTRUCTION_FAILED",
                "gap_range_searched": [min_gap, max_gap],
                "valid_candidate_count": 0,
                "note": (
                    "No gap size in [min_gap, max_gap] produced a valid artifact. "
                    "Fragments remain separate."
                ),
            },
        )
