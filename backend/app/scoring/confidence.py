"""
confidence.py — Deterministic recovery confidence scoring engine and status classification.

Computes recovery confidence scores (0–100) across 5 locked dimensions, classifies recovery
status based on exact thresholds and critical reconstructed-byte override rules, and constructs
honest forensic provenance metadata.

Locked Component Weights:
  - Header validity:          20 points
  - Footer/end marker:        20 points
  - Structural validation:    30 points
  - Size plausibility:        15 points
  - Reconstruction integrity: 15 points
Total: 100 points.

Status Thresholds & Rules:
  - 85–100 → FULLY_RECOVERED (Unless reconstructed_bytes > 0)
  - 50–84  → PARTIALLY_RECOVERED
  - 20–49  → CORRUPTED
  - 0–19   → UNRECOVERABLE

Critical Forensic Override:
  If reconstructed_bytes > 0 and numeric threshold result is FULLY_RECOVERED,
  it is strictly downgraded to PARTIALLY_RECOVERED. Otherwise, the numeric threshold
  result is preserved.
"""

from __future__ import annotations

from typing import Union, Optional, Any

from backend.app.models.validation import ValidationResult
from backend.app.models.reconstruction import BifragmentReconstructionResult
from backend.app.models.confidence import (
    RecoveryStatus,
    ConfidenceBreakdown,
    ArtifactProvenance,
    ConfidenceEvaluationResult,
)
from backend.app.recovery.carver import RecoveredArtifact
from backend.app.recovery.signatures import (
    SYNTHETIC_START_MARKER,
    SYNTHETIC_END_MARKER,
)


def calculate_confidence(
    validation_result: ValidationResult,
    reconstruction_result: Optional[BifragmentReconstructionResult] = None,
    artifact: Optional[Union[RecoveredArtifact, bytes, bytearray]] = None,
) -> ConfidenceBreakdown:
    """Calculate deterministic confidence score breakdown across 5 component dimensions.

    Args:
        validation_result: Structural validation result from Task 5.
        reconstruction_result: Bounded bifragment reconstruction result from Task 6 (optional).
        artifact: Recovered artifact bytes or object (optional).

    Returns:
        ConfidenceBreakdown detailing scores for header, footer, validation,
        size plausibility, reconstruction integrity, and total score.

    Raises:
        TypeError: If validation_result is not a ValidationResult instance.
    """
    if not isinstance(validation_result, ValidationResult):
        raise TypeError(f"Expected ValidationResult, got {type(validation_result)}")

    # 1. Header Validity (max 20 points)
    header_score = 0
    has_header_error = any("start marker" in err.lower() for err in validation_result.errors)
    if not has_header_error:
        if validation_result.valid or "start_marker_exists" in validation_result.checks_performed:
            header_score = 20

    # 2. Footer Validity (max 20 points)
    footer_score = 0
    has_footer_error = any("end marker" in err.lower() for err in validation_result.errors)
    if not has_footer_error:
        if validation_result.valid or "end_marker_exists" in validation_result.checks_performed:
            footer_score = 20

    # 3. Structural Validation (max 30 points)
    structural_score = 30 if validation_result.valid else 0

    # 4. Provenance & Byte Accounting (pre-calculation for size plausibility)
    provenance = build_provenance(validation_result, reconstruction_result, artifact)

    # 5. Size Plausibility (max 15 points)
    # Deterministic criteria:
    #   a) Non-empty artifact (verified_bytes > 0)
    #   b) Byte accounting consistent (verified_bytes >= 0, reconstructed_bytes >= 0, missing_bytes >= 0)
    #   c) No size/length errors reported in validation errors (e.g. "empty", "truncated")
    #   d) If bifragment, gap size is within valid bounds [1, 4096]
    size_score = 0
    has_size_error = any(kw in err.lower() for err in validation_result.errors for kw in ["empty", "zero", "truncated"])
    accounting_valid = (
        provenance.verified_bytes > 0
        and provenance.reconstructed_bytes >= 0
        and provenance.missing_bytes >= 0
    )

    if accounting_valid and not has_size_error:
        if reconstruction_result is not None:
            if reconstruction_result.success:
                if (
                    reconstruction_result.gap_size is not None
                    and 1 <= reconstruction_result.gap_size <= 4096
                    and reconstruction_result.missing_byte_count == reconstruction_result.gap_size
                ):
                    size_score = 15
            else:
                # Failed reconstruction means gap/size integrity cannot be verified
                size_score = 0
        else:
            # Contiguous artifact with non-empty verified bytes and valid boundaries
            size_score = 15

    # 6. Reconstruction Integrity (max 15 points)
    reconstruction_score = 0
    if validation_result.valid and (reconstruction_result is None or reconstruction_result.reconstruction_method in ("NONE", "CONTIGUOUS")):
        # Contiguous artifact requiring no reconstruction
        reconstruction_score = 15
    elif reconstruction_result is not None:
        # Bounded bifragment reconstruction attempted
        if reconstruction_result.success:
            if (
                reconstruction_result.gap_size is not None
                and 1 <= reconstruction_result.gap_size <= 4096
                and reconstruction_result.missing_byte_count == reconstruction_result.gap_size
                and reconstruction_result.validation_result is not None
                and reconstruction_result.validation_result.valid
            ):
                reconstruction_score = 15
            else:
                reconstruction_score = 0
        else:
            # Failed reconstruction gets 0 integrity points
            reconstruction_score = 0

    # Ensure component maximum bounds defensively
    header_score = min(20, max(0, header_score))
    footer_score = min(20, max(0, footer_score))
    structural_score = min(30, max(0, structural_score))
    size_score = min(15, max(0, size_score))
    reconstruction_score = min(15, max(0, reconstruction_score))

    total = header_score + footer_score + structural_score + size_score + reconstruction_score
    total = min(100, max(0, total))

    return ConfidenceBreakdown(
        header_validity=header_score,
        footer_validity=footer_score,
        structural_validation=structural_score,
        size_plausibility=size_score,
        reconstruction_integrity=reconstruction_score,
        total=total,
    )


def classify_recovery_status(
    score: int,
    reconstructed_bytes: int = 0,
    missing_bytes: int = 0,
) -> RecoveryStatus:
    """Classify recovery status based on confidence score and critical override rules.

    Thresholds:
      - 85–100 → FULLY_RECOVERED (Unless reconstructed_bytes > 0)
      - 50–84  → PARTIALLY_RECOVERED
      - 20–49  → CORRUPTED
      - 0–19   → UNRECOVERABLE

    Critical Override Rule:
      If reconstructed_bytes > 0 and the numeric threshold result is FULLY_RECOVERED,
      it is strictly downgraded to PARTIALLY_RECOVERED.
      Otherwise, the numeric threshold result is preserved.

    Args:
        score: Numeric confidence score (0–100).
        reconstructed_bytes: Number of reconstructed bytes.
        missing_bytes: Number of unobserved/missing bytes.

    Returns:
        RecoveryStatus enum value.
    """
    if score < 0 or score > 100:
        raise ValueError(f"Score must be between 0 and 100, got {score}")

    if reconstructed_bytes < 0:
        raise ValueError(f"reconstructed_bytes cannot be negative: {reconstructed_bytes}")

    if missing_bytes < 0:
        raise ValueError(f"missing_bytes cannot be negative: {missing_bytes}")

    if score >= 85:
        status = RecoveryStatus.FULLY_RECOVERED
    elif score >= 50:
        status = RecoveryStatus.PARTIALLY_RECOVERED
    elif score >= 20:
        status = RecoveryStatus.CORRUPTED
    else:
        status = RecoveryStatus.UNRECOVERABLE

    if reconstructed_bytes > 0 and status == RecoveryStatus.FULLY_RECOVERED:
        return RecoveryStatus.PARTIALLY_RECOVERED

    return status


def build_provenance(
    validation_result: ValidationResult,
    reconstruction_result: Optional[BifragmentReconstructionResult] = None,
    artifact: Optional[Union[RecoveredArtifact, bytes, bytearray]] = None,
) -> ArtifactProvenance:
    """Build lightweight forensic provenance metadata for a recovered artifact.

    Args:
        validation_result: ValidationResult from Task 5.
        reconstruction_result: BifragmentReconstructionResult from Task 6 (optional).
        artifact: Recovered artifact bytes or object (optional).

    Returns:
        ArtifactProvenance metadata structure.
    """
    verified_bytes = 0
    reconstructed_bytes = 0
    missing_bytes = 0
    reconstruction_method = "NONE"

    if reconstruction_result is not None and isinstance(reconstruction_result, BifragmentReconstructionResult):
        verified_bytes = len(reconstruction_result.fragment_a_bytes) + len(reconstruction_result.fragment_b_bytes)
        reconstructed_bytes = 0  # Missing gap bytes are NEVER synthesized as recovered evidence
        missing_bytes = reconstruction_result.missing_byte_count if reconstruction_result.success else 0
        reconstruction_method = reconstruction_result.reconstruction_method
    elif artifact is not None:
        if isinstance(artifact, RecoveredArtifact):
            verified_bytes = artifact.recovered_byte_count
        elif isinstance(artifact, (bytes, bytearray)):
            verified_bytes = len(artifact)
        reconstructed_bytes = 0
        missing_bytes = 0
        reconstruction_method = "NONE"
    elif validation_result is not None and hasattr(validation_result, "details"):
        # Extract from validation details if provided
        verified_bytes = validation_result.details.get("byte_count", 0)

    val_status = "PASSED" if (validation_result and validation_result.valid) else "FAILED"

    return ArtifactProvenance(
        verified_bytes=verified_bytes,
        reconstructed_bytes=reconstructed_bytes,
        missing_bytes=missing_bytes,
        reconstruction_method=reconstruction_method,
        validation_status=val_status,
    )


def evaluate_artifact_confidence(
    validation_result: ValidationResult,
    reconstruction_result: Optional[BifragmentReconstructionResult] = None,
    artifact: Optional[Union[RecoveredArtifact, bytes, bytearray]] = None,
) -> ConfidenceEvaluationResult:
    """Evaluate confidence breakdown, status classification, and provenance for an artifact.

    Args:
        validation_result: ValidationResult from Task 5.
        reconstruction_result: BifragmentReconstructionResult from Task 6 (optional).
        artifact: Recovered artifact bytes or object (optional).

    Returns:
        ConfidenceEvaluationResult combining breakdown, status, and provenance.
    """
    provenance = build_provenance(validation_result, reconstruction_result, artifact)
    breakdown = calculate_confidence(validation_result, reconstruction_result, artifact)
    status = classify_recovery_status(
        score=breakdown.total,
        reconstructed_bytes=provenance.reconstructed_bytes,
        missing_bytes=provenance.missing_bytes,
    )

    return ConfidenceEvaluationResult(
        score_breakdown=breakdown,
        status=status,
        provenance=provenance,
    )

