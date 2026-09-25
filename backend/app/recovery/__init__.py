"""
Recoverix — Recovery Layer

Scans raw evidence bytes for known format signatures, produces
deterministic candidate fragment records, carved artifacts, and structural validators.

This layer does NOT perform reconstruction, repair, structural
validation, confidence scoring, classification, or AI work.
"""

from backend.app.models.validation import ValidationResult
from backend.app.recovery.signatures import (
    FormatSignature,
    SIGNATURES,
)
from backend.app.recovery.scanner import (
    Candidate,
    scan_evidence,
)
from backend.app.recovery.carver import (
    RecoveredArtifact,
    carve_candidate,
)
from backend.app.recovery.validators import (
    validate_txt,
    validate_csv,
)

__all__ = [
    "ValidationResult",
    "FormatSignature",
    "SIGNATURES",
    "Candidate",
    "scan_evidence",
    "RecoveredArtifact",
    "carve_candidate",
    "validate_txt",
    "validate_csv",
]
