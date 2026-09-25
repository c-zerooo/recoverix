"""
validation.py — Validation result data model.

Represents the deterministic outcome of structural validation for a recovered artifact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass(frozen=True)
class ValidationResult:
    """Result of structural validation on a recovered artifact.

    Attributes:
        valid: Whether the artifact passes all structural checks.
        format: Format of the artifact ("txt", "csv", etc.).
        checks_performed: List of check descriptions that were executed.
        errors: List of error messages if validation failed.
        warnings: List of non-fatal warning messages.
        details: Additional format-specific metrics or details.
    """

    valid: bool
    format: str
    checks_performed: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
