"""
evidence_graph.py — API router for Evidence Relationship Graph & Artifact Clustering.

Milestone 3.4: Exposes read-only endpoint GET /api/cases/{case_id}/graph.
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status

from backend.app.models.evidence_graph import EvidenceGraph
from backend.app.recovery.graph import build_case_evidence_graph
from backend.app.store import store

router = APIRouter(prefix="/cases", tags=["evidence_graph"])


@router.get(
    "/{case_id}/graph",
    response_model=EvidenceGraph,
    status_code=status.HTTP_200_OK,
    summary="Get case evidence relationship graph and artifact clusters",
)
def get_case_evidence_graph(
    case_id: str,
    evidence_file_id: Optional[str] = Query(
        default=None,
        description="Optional filter to restrict graph to a specific evidence buffer",
    ),
) -> EvidenceGraph:
    """Retrieve the deterministic Evidence Relationship Graph and Artifact Clusters for a case.

    Operates strictly as an interpretation and projection layer over persisted recovery data.
    Does NOT accept raw evidence bytes and does NOT re-run recovery.
    """
    case = store.get_case(case_id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' not found",
        )

    try:
        return build_case_evidence_graph(
            case_id=case_id,
            store=store,
            evidence_file_id=evidence_file_id,
        )
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )
