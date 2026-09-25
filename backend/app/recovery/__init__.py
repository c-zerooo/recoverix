"""
Recoverix — Recovery Layer

Scans raw evidence bytes for known format signatures, produces
deterministic candidate fragment records, carved artifacts, structural validators,
and bounded bifragment reconstruction.

This layer does NOT perform confidence scoring, classification, prioritization, or AI work.
"""

from backend.app.models.validation import ValidationResult
from backend.app.models.reconstruction import BifragmentReconstructionResult
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
from backend.app.recovery.bifragment import (
    reconstruct_bifragment,
)

__all__ = [
    "ValidationResult",
    "BifragmentReconstructionResult",
    "FormatSignature",
    "SIGNATURES",
    "Candidate",
    "scan_evidence",
    "RecoveredArtifact",
    "carve_candidate",
    "validate_txt",
    "validate_csv",
    "reconstruct_bifragment",
]
