"""
carver.py — Deterministic contiguous artifact carver.

Accepts raw evidence bytes and a Candidate object, and extracts the
candidate's contiguous byte region safely.

This module does NOT perform structural validation, PNG parsing,
bifragment reconstruction, confidence scoring, classification, or AI work.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.app.recovery.scanner import Candidate


@dataclass(frozen=True)
class RecoveredArtifact:
    """A contiguously carved artifact region from evidence.

    Attributes:
        candidate_id: Unique identifier of spatial candidate.
        format: Detected format ("txt", "csv", "png").
        mime_type: MIME type string.
        category: Human-readable category ("text", "image").
        source_offset: Byte offset where the artifact starts in the evidence.
        recovered_bytes: Raw carved bytes of the artifact.
        recovered_byte_count: Number of bytes successfully carved.
        carving_method: Method used to carve ("CONTIGUOUS").
    """

    candidate_id: str
    format: str
    mime_type: str
    category: str
    source_offset: int
    recovered_bytes: bytes
    recovered_byte_count: int
    carving_method: str = "CONTIGUOUS"


def carve_candidate(evidence: bytes, candidate: Candidate) -> RecoveredArtifact:
    """Extract a contiguous artifact region from *evidence* based on *candidate*.

    Args:
        evidence: Raw evidence bytes. Never mutated.
        candidate: Candidate object identifying the region to carve.

    Returns:
        A RecoveredArtifact containing the carved bytes.

    Raises:
        ValueError: If evidence is empty, candidate boundaries are invalid,
            out of bounds, zero-length, or if estimated_end_offset is missing (None).
        TypeError: If candidate is not a Candidate instance.
    """
    if not isinstance(candidate, Candidate):
        raise TypeError(f"Expected Candidate object, got {type(candidate)}")

    if len(evidence) == 0:
        raise ValueError("Cannot carve from empty evidence")

    if candidate.offset < 0:
        raise ValueError(f"Candidate offset cannot be negative: {candidate.offset}")

    if candidate.estimated_end_offset is None:
        raise ValueError(
            f"Cannot contiguously carve candidate '{candidate.candidate_id}' "
            f"({candidate.format}): estimated_end_offset is None (no known end boundary)"
        )

    start = candidate.offset
    end = candidate.estimated_end_offset

    if end < start:
        raise ValueError(
            f"Candidate estimated_end_offset ({end}) cannot be less than offset ({start})"
        )

    if end > len(evidence):
        raise ValueError(
            f"Candidate region [{start}, {end}) exceeds evidence size ({len(evidence)})"
        )

    if start == end:
        raise ValueError(f"Candidate region has zero length (offset {start})")

    recovered = evidence[start:end]
    byte_count = len(recovered)

    if byte_count == 0:
        raise ValueError(f"Carved zero bytes for candidate '{candidate.candidate_id}'")

    if byte_count != (end - start):
        raise ValueError(
            f"Carved byte count ({byte_count}) does not match expected range ({end - start})"
        )

    return RecoveredArtifact(
        candidate_id=candidate.candidate_id,
        format=candidate.format,
        mime_type=candidate.mime_type,
        category=candidate.category,
        source_offset=start,
        recovered_bytes=recovered,
        recovered_byte_count=byte_count,
        carving_method="CONTIGUOUS",
    )
