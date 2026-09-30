"""
interpretation.py — Immutable Pydantic v2 models for Grounded Evidence Interpretation.

Milestone 3.5: Grounded interpretation core, fact contracts, and persistence models.
"""

from __future__ import annotations

from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, ConfigDict, Field

# Complete, authoritative Recoverix status vocabulary preserved exactly
AuthoritativeRecoveryStatus = Literal[
    "FULLY_RECOVERED",
    "PARTIALLY_RECOVERED",
    "CORRUPTED",
    "UNRECOVERABLE",
]

# Exact Milestone 3.4 cluster classifications preserved exactly
AuthoritativeClusterClassification = Literal[
    "ISOLATED",
    "COEXTENSIVE_SET",
    "CONTAINMENT_TREE",
    "OVERLAP_SPAN",
    "MIXED",
]


class DeterministicArtifactFacts(BaseModel):
    """Immutable deterministic facts extracted for a single recovery artifact."""

    model_config = ConfigDict(frozen=True)

    artifact_id: str
    run_id: Optional[str] = None
    case_id: Optional[str] = None
    evidence_file_id: Optional[str] = None
    filename: str
    format: str
    category: str = "DOCUMENT"
    status: AuthoritativeRecoveryStatus
    confidence_score: float = Field(ge=0.0, le=100.0)
    priority: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    verified_bytes: int = Field(ge=0)
    reconstructed_bytes: int = Field(ge=0)
    missing_bytes: int = Field(ge=0)
    total_input_bytes: Optional[int] = Field(default=None, ge=0)
    reconstruction_method: str = "NONE"
    validation_status: str = "VALID"
    damage_region_count: int = Field(default=0, ge=0)
    is_ambiguous: bool = False
    evidence_start: Optional[int] = Field(default=None, ge=0)
    evidence_end: Optional[int] = Field(default=None, ge=0)


class DeterministicRelationshipFact(BaseModel):
    """Immutable typed spatial relationship fact derived from a Milestone 3.4 GraphEdge."""

    model_config = ConfigDict(frozen=True)

    edge_id: str
    source_node_id: str
    target_node_id: str
    relationship_type: Literal["COEXTENSIVE", "CONTAINS", "CONTAINED_BY", "OVERLAPS"]
    evidence_file_id: str
    evidence_basis: str
    overlap_start: Optional[int] = None
    overlap_end: Optional[int] = None
    overlap_bytes: int = Field(default=0, ge=0)


class DeterministicClusterFacts(BaseModel):
    """Immutable deterministic facts extracted for a spatial artifact cluster."""

    model_config = ConfigDict(frozen=True)

    cluster_id: str
    case_id: str
    evidence_file_id: Optional[str] = None
    cluster_start: int = Field(ge=0)
    cluster_end: Optional[int] = Field(default=None, ge=0)
    relationship_classification: AuthoritativeClusterClassification
    has_ambiguity: bool
    total_nodes: int = Field(ge=1)
    member_formats: List[str]
    member_node_ids: List[str]
    max_confidence_score: float = Field(ge=0.0, le=100.0)
    highest_priority: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]


class DeterministicCaseFacts(BaseModel):
    """Immutable deterministic facts aggregated across a complete case."""

    model_config = ConfigDict(frozen=True)

    case_id: str
    total_evidence_buffers: int = Field(ge=0)
    total_artifacts: int = Field(ge=0)
    total_nodes: int = Field(ge=0)
    total_clusters: int = Field(ge=0)
    format_distribution: Dict[str, int]
    status_distribution: Dict[str, int]
    priority_distribution: Dict[str, int]
    cluster_classification_distribution: Dict[str, int]
    candidate_cap_enforced: bool = False
    total_discovered_candidates: int = Field(default=0, ge=0)
    candidates_omitted: int = Field(default=0, ge=0)


class ArtifactInterpretationContext(BaseModel):
    """Context supplied to an interpretation provider for an artifact."""

    model_config = ConfigDict(frozen=True)

    facts: DeterministicArtifactFacts
    content_preview: Optional[str] = Field(
        default=None,
        description="Sanitized, truncated preview (<= 200 chars). Raw bytes are strictly excluded.",
    )
    cluster_context: Optional[DeterministicClusterFacts] = None


class ClusterInterpretationContext(BaseModel):
    """Context supplied to an interpretation provider for a spatial cluster."""

    model_config = ConfigDict(frozen=True)

    facts: DeterministicClusterFacts
    nodes: List[DeterministicArtifactFacts]
    relationships: List[DeterministicRelationshipFact]


class CaseInterpretationContext(BaseModel):
    """Context supplied to an interpretation provider for an entire case."""

    model_config = ConfigDict(frozen=True)

    facts: DeterministicCaseFacts


class ProviderInterpretationOutput(BaseModel):
    """Pure interpretive output produced by an InterpretationProvider.

    Contains ZERO system-owned facts (no priority, score, status, byte counts).
    """

    model_config = ConfigDict(frozen=True)

    summary: str = Field(
        description="Concise 1-2 sentence executive overview of the recovery finding."
    )
    assessment: str = Field(
        description="Detailed forensic analysis of what the surviving structural bytes establish."
    )
    structural_context: str = Field(
        description="Technical explanation of format markers, delimiters, and reconstruction validity."
    )
    limitations: str = Field(
        description="Explicit declaration of unobserved data, missing bytes, or format ambiguities."
    )
    recommended_next_steps: str = Field(
        description="Actionable forensic investigation steps for examiners."
    )
    details: List[str] = Field(
        default_factory=list,
        description="Structured bullet-point statements for UI presentation.",
    )


class GroundedArtifactInterpretation(BaseModel):
    """Complete, bound evidence interpretation for a single artifact."""

    model_config = ConfigDict(frozen=True)

    facts: DeterministicArtifactFacts
    interpretation: ProviderInterpretationOutput
    source: Literal["DETERMINISTIC_RULES", "GEMINI_1_5_FLASH"]
    cached: bool = False
    generated_at: str

    def with_cached(self, cached: bool) -> GroundedArtifactInterpretation:
        """Return a copy with updated cached flag."""
        return self.model_copy(update={"cached": cached})

    def to_legacy_dict(self) -> Dict[str, Any]:
        """Convert to the legacy AIExplanation dictionary for backward compatibility."""
        score_val: Any = (
            int(self.facts.confidence_score)
            if float(self.facts.confidence_score).is_integer()
            else round(self.facts.confidence_score, 2)
        )
        return {
            "summary": self.interpretation.summary,
            "details": list(self.interpretation.details),
            "assessment": self.interpretation.assessment,
            "priority": self.facts.priority,  # Authoritative system fact!
            "why_it_matters": self.interpretation.structural_context,
            "recovery_limitation": self.interpretation.limitations,
            "recommended_next_step": self.interpretation.recommended_next_steps,
            "available": True,
            "cached": self.cached,
            "source": self.source,
            "facts": {
                "verified_bytes": self.facts.verified_bytes,
                "reconstructed_bytes": self.facts.reconstructed_bytes,
                "missing_bytes": self.facts.missing_bytes,
                "status": self.facts.status,
                "format": self.facts.format,
                "confidence_score": score_val,
                "reconstruction_method": self.facts.reconstruction_method,
                "validation_status": self.facts.validation_status,
            },
        }


class GroundedClusterInterpretation(BaseModel):
    """Complete, bound evidence interpretation for an artifact cluster."""

    model_config = ConfigDict(frozen=True)

    facts: DeterministicClusterFacts
    relationships: List[DeterministicRelationshipFact]
    interpretation: ProviderInterpretationOutput
    source: Literal["DETERMINISTIC_RULES", "GEMINI_1_5_FLASH"]
    cached: bool = False
    generated_at: str


class GroundedCaseInterpretation(BaseModel):
    """Complete, bound forensic briefing for an entire case."""

    model_config = ConfigDict(frozen=True)

    facts: DeterministicCaseFacts
    interpretation: ProviderInterpretationOutput
    source: Literal["DETERMINISTIC_RULES", "GEMINI_1_5_FLASH"]
    cached: bool = False
    generated_at: str
