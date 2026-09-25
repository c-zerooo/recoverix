"""
confidence.py — Confidence scoring, recovery status, and provenance data models.

Represents deterministic recovery confidence score breakdowns, recovery status classifications,
and lightweight forensic artifact provenance metadata.

Forensic Principle:
  - Confidence scoring is 100% deterministic (weights sum to 100).
  - Missing/reconstructed bytes strictly override FULLY_RECOVERED status classification.
  - Provenance byte accounting strictly distinguishes between verified bytes,
    reconstructed bytes, and unobserved missing bytes without AI infill synthesis.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class RecoveryStatus(str, Enum):
    """Enumeration of deterministic recovery status classifications."""

    FULLY_RECOVERED = "FULLY_RECOVERED"
    PARTIALLY_RECOVERED = "PARTIALLY_RECOVERED"
    CORRUPTED = "CORRUPTED"
    UNRECOVERABLE = "UNRECOVERABLE"


@dataclass(frozen=True)
class ConfidenceBreakdown:
    """Detailed score breakdown across 5 locked component dimensions.

    Component Weights (Total = 100):
      - header_validity: max 20 points
      - footer_validity: max 20 points
      - structural_validation: max 30 points
      - size_plausibility: max 15 points
      - reconstruction_integrity: max 15 points
    """

    header_validity: int
    footer_validity: int
    structural_validation: int
    size_plausibility: int
    reconstruction_integrity: int
    total: int

    def __post_init__(self) -> None:
        """Enforce component maximum bounds defensively."""
        if not (0 <= self.header_validity <= 20):
            raise ValueError(f"header_validity must be in [0, 20], got {self.header_validity}")
        if not (0 <= self.footer_validity <= 20):
            raise ValueError(f"footer_validity must be in [0, 20], got {self.footer_validity}")
        if not (0 <= self.structural_validation <= 30):
            raise ValueError(f"structural_validation must be in [0, 30], got {self.structural_validation}")
        if not (0 <= self.size_plausibility <= 15):
            raise ValueError(f"size_plausibility must be in [0, 15], got {self.size_plausibility}")
        if not (0 <= self.reconstruction_integrity <= 15):
            raise ValueError(f"reconstruction_integrity must be in [0, 15], got {self.reconstruction_integrity}")
        if not (0 <= self.total <= 100):
            raise ValueError(f"total score must be in [0, 100], got {self.total}")


@dataclass(frozen=True)
class ArtifactProvenance:
    """Lightweight forensic provenance metadata for a recovered artifact.

    Attributes:
        verified_bytes: Number of original, known, verified bytes.
        reconstructed_bytes: Number of reconstructed bytes (0 unless structurally defined).
        missing_bytes: Number of unobserved/missing bytes in unknown gaps.
        reconstruction_method: Method identifier ("NONE", "BIFRAGMENT_GAP", etc.).
        validation_status: Status string ("VALID", "INVALID").
    """

    verified_bytes: int
    reconstructed_bytes: int
    missing_bytes: int
    reconstruction_method: str
    validation_status: str

    def __post_init__(self) -> None:
        """Enforce byte accounting invariants defensively."""
        if self.verified_bytes < 0:
            raise ValueError(f"verified_bytes cannot be negative: {self.verified_bytes}")
        if self.reconstructed_bytes < 0:
            raise ValueError(f"reconstructed_bytes cannot be negative: {self.reconstructed_bytes}")
        if self.missing_bytes < 0:
            raise ValueError(f"missing_bytes cannot be negative: {self.missing_bytes}")
        if "AI_PREDICTED_INFILL" in self.reconstruction_method:
            raise ValueError("Forbidden terminology: AI_PREDICTED_INFILL is strictly prohibited.")


@dataclass(frozen=True)
class ConfidenceEvaluationResult:
    """Complete evaluation outcome combining score breakdown, status classification, and provenance."""

    score_breakdown: ConfidenceBreakdown
    status: RecoveryStatus
    provenance: ArtifactProvenance
