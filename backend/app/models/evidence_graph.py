"""
evidence_graph.py — Immutable Pydantic v2 models for Evidence Relationship Graph & Clustering.

Milestone 3.4: Deterministic directed, labeled evidence relationship graph and artifact clustering.
"""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class GraphNode(BaseModel):
    """Immutable node representing an evaluated recovery candidate/artifact in the evidence graph."""

    model_config = ConfigDict(frozen=True)

    node_id: str
    candidate_id: Optional[str] = None
    run_id: str
    artifact_id: Optional[str] = None
    evidence_file_id: Optional[str] = None
    format: str
    evidence_start: int
    evidence_end: Optional[int] = None
    coordinate_system: str
    status: str
    confidence_score: float
    verified_bytes: int
    reconstructed_bytes: int
    missing_bytes: int
    detection_method: str
    is_ambiguous: bool


class GraphEdge(BaseModel):
    """Immutable directed edge representing a verified spatial relationship between two nodes."""

    model_config = ConfigDict(frozen=True)

    edge_id: str
    source_node_id: str
    target_node_id: str
    relationship_type: str
    evidence_file_id: str
    evidence_basis: str
    overlap_start: Optional[int] = None
    overlap_end: Optional[int] = None
    overlap_bytes: int


class ArtifactCluster(BaseModel):
    """Immutable connected component of spatially interrelated nodes within one evidence buffer."""

    model_config = ConfigDict(frozen=True)

    cluster_id: str
    evidence_file_id: Optional[str] = None
    cluster_start: int
    cluster_end: Optional[int] = None
    node_ids: List[str]
    formats: List[str]
    relationship_classification: str
    has_ambiguity: bool
    total_nodes: int


class EvidenceBufferSummary(BaseModel):
    """Summary of nodes, edges, clusters, and candidate-cap status for an individual evidence buffer."""

    model_config = ConfigDict(frozen=True)

    evidence_file_id: str
    total_nodes: int
    total_edges: int
    total_clusters: int
    total_byte_span: Optional[int] = None
    candidate_cap_enforced: bool
    total_discovered_candidates: int
    candidates_omitted: int
    buffer_is_complete: bool


class EvidenceGraphMetadata(BaseModel):
    """Forensic execution metadata and aggregated candidate-cap statistics for the case graph."""

    model_config = ConfigDict(frozen=True)

    case_id: Optional[str] = None
    total_evidence_buffers: int
    total_nodes: int
    total_edges: int
    total_clusters: int
    candidate_cap_enforced: bool
    total_discovered_candidates: int
    candidates_omitted: int
    graph_is_complete: bool


class EvidenceGraph(BaseModel):
    """Root immutable container for the complete evidence relationship graph."""

    model_config = ConfigDict(frozen=True)

    case_id: Optional[str] = None
    evidence_buffers: List[EvidenceBufferSummary] = Field(default_factory=list)
    nodes: List[GraphNode] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)
    clusters: List[ArtifactCluster] = Field(default_factory=list)
    metadata: EvidenceGraphMetadata
