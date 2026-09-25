"""
reconstruction.py — Bounded bifragment reconstruction data models.

Represents the forensic outcome of bounded bifragment reconstruction between two
recovered fragments separated by an unknown gap.

Forensic Invariant:
  Known bytes from Fragment A and Fragment B are preserved exactly as recovered.
  Unknown missing bytes in the gap are recorded purely as metadata (gap size / range)
  and are NEVER fabricated, guessed, or presented as recovered evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

from backend.app.models.validation import ValidationResult


@dataclass(frozen=True)
class BifragmentReconstructionResult:
    """Result of bounded bifragment reconstruction across an unknown gap.

    Attributes:
        success: Whether a valid gap size was found that satisfies structural validation.
        format: Format identifier ("txt", "csv", etc.).
        fragment_a_id: Identifier or source reference for Fragment A.
        fragment_b_id: Identifier or source reference for Fragment B.
        gap_size: Selected smallest valid gap size in bytes, or None if reconstruction failed.
        missing_byte_count: Number of missing/unknown bytes in the gap (0 if failed).
        reconstruction_method: Method used (default "BOUNDED_BIFRAGMENT").
        validation_result: Structural validation result for the candidate reconstruction, or None.
        valid_candidate_count: Total number of gap sizes in [min_gap, max_gap] that validated.
        fragment_a_bytes: Exact recovered bytes of Fragment A (never mutated).
        fragment_b_bytes: Exact recovered bytes of Fragment B (never mutated).
        missing_region_metadata: Forensic metadata describing the missing region without fabricating bytes.
    """

    success: bool
    format: str
    fragment_a_id: str
    fragment_b_id: str
    gap_size: Optional[int]
    missing_byte_count: int
    reconstruction_method: str = "BIFRAGMENT_GAP"
    validation_result: Optional[ValidationResult] = None
    valid_candidate_count: int = 0
    fragment_a_bytes: bytes = field(default_factory=bytes)
    fragment_b_bytes: bytes = field(default_factory=bytes)
    missing_region_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReconstructionResult:
    """Forensic result of format-specific deterministic reconstruction.

    Attributes:
        format: Format identifier ("txt", "csv", "json", "xml", "png", "jpeg", "pdf").
        status: High-level recovery status ("FULLY_RECOVERED", "PARTIALLY_RECOVERED", "UNRECOVERABLE").
        success: Whether a structurally valid output file was produced.
        recovered_bytes: Raw usable reconstructed file bytes (never synthetic filler).
        verified_bytes: Count of bytes in recovered_bytes that came directly from evidence.
        reconstructed_bytes: Count of deterministic structural repair bytes added to achieve validity.
        missing_bytes: Count of evidence bytes lost or destroyed that remain unrecoverable.
        damage_regions: List of detected damage regions (offsets, length, type, status).
        reconstruction_methods: List of deterministic techniques applied.
        validation_result: Structural validation result for recovered_bytes.
        is_exact_match: Optional boolean indicating SHA-256 equality with ground truth.
        details: Additional forensic diagnostics and metadata.
    """

    format: str
    status: str
    success: bool
    recovered_bytes: bytes
    verified_bytes: int
    reconstructed_bytes: int
    missing_bytes: int
    damage_regions: List[Dict[str, Any]] = field(default_factory=list)
    reconstruction_methods: List[str] = field(default_factory=list)
    validation_result: Optional[ValidationResult] = None
    is_exact_match: Optional[bool] = None
    details: Dict[str, Any] = field(default_factory=dict)

