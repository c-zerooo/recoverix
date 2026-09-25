"""
Recoverix — Recovery Layer

Scans raw evidence bytes for known format signatures and produces
deterministic candidate fragment records and carved artifacts.

This layer does NOT perform reconstruction, repair, structural
validation, confidence scoring, classification, or AI work.
"""

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

__all__ = [
    "FormatSignature",
    "SIGNATURES",
    "Candidate",
    "scan_evidence",
    "RecoveredArtifact",
    "carve_candidate",
]
