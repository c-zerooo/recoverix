"""
artifact.py — Artifact API models for Recoverix platform.
"""

from __future__ import annotations

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class ConfidenceBreakdownSchema(BaseModel):
    """Confidence score breakdown across 5 component dimensions."""

    header_validity: int
    footer_validity: int
    structural_validation: int
    size_plausibility: int
    reconstruction_integrity: int
    total: int


class ArtifactProvenanceSchema(BaseModel):
    """Forensic provenance byte accounting and status metadata."""

    verified_bytes: int
    reconstructed_bytes: int
    missing_bytes: int
    reconstruction_method: str
    validation_status: str


class ArtifactResponse(BaseModel):
    """API-facing representation of a recovered artifact."""

    artifact_id: str
    case_id: str
    format: str
    size_bytes: int
    confidence_score: int
    score_breakdown: ConfidenceBreakdownSchema
    status: str
    provenance: ArtifactProvenanceSchema
    category: Optional[str] = None
    priority: Optional[str] = None
    ai_summary: Optional[str] = None
    content_preview: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
