"""
interpretation.py — API router for Grounded Evidence Interpretation.

Milestone 3.5.3.1: Router setup and response contract wiring.
Exposes canonical endpoints for artifact, cluster, and case interpretations.
Actual execution and retrieval behaviors are implemented in subsequent phases.
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status

from backend.app.models.interpretation import (
    GroundedArtifactInterpretation,
    GroundedClusterInterpretation,
    GroundedCaseInterpretation,
)

router = APIRouter(tags=["interpretation"])


@router.get(
    "/artifacts/{artifact_id}/interpretation",
    response_model=GroundedArtifactInterpretation,
    status_code=status.HTTP_200_OK,
    summary="Get grounded artifact interpretation",
)
def get_artifact_interpretation(artifact_id: str) -> GroundedArtifactInterpretation:
    """Retrieve persisted grounded evidence interpretation for an artifact.

    Strictly read-only: does not generate interpretation, invoke LLMs, or mutate storage.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Artifact interpretation retrieval will be implemented in Phase 3.5.3.3",
    )


@router.post(
    "/artifacts/{artifact_id}/interpretation",
    response_model=GroundedArtifactInterpretation,
    status_code=status.HTTP_200_OK,
    summary="Generate or refresh grounded artifact interpretation",
)
def generate_artifact_interpretation(
    artifact_id: str,
    force_refresh: bool = Query(
        default=False,
        description="Whether to force regeneration and overwrite existing persisted interpretation",
    ),
) -> GroundedArtifactInterpretation:
    """Generate or refresh grounded evidence interpretation for an artifact."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Artifact interpretation generation will be implemented in Phase 3.5.3.3",
    )


@router.get(
    "/cases/{case_id}/clusters/{cluster_id}/interpretation",
    response_model=GroundedClusterInterpretation,
    status_code=status.HTTP_200_OK,
    summary="Get grounded cluster interpretation",
)
def get_cluster_interpretation(
    case_id: str,
    cluster_id: str,
) -> GroundedClusterInterpretation:
    """Retrieve cached grounded evidence interpretation for a spatial cluster.

    Strictly read-only: does not generate interpretation, invoke LLMs, or mutate cache.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Cluster interpretation retrieval will be implemented in Phase 3.5.3.4",
    )


@router.post(
    "/cases/{case_id}/clusters/{cluster_id}/interpretation",
    response_model=GroundedClusterInterpretation,
    status_code=status.HTTP_200_OK,
    summary="Generate or refresh grounded cluster interpretation",
)
def generate_cluster_interpretation(
    case_id: str,
    cluster_id: str,
    force_refresh: bool = Query(
        default=False,
        description="Whether to force regeneration and replace cache entry",
    ),
) -> GroundedClusterInterpretation:
    """Generate or refresh grounded evidence interpretation for a spatial cluster."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Cluster interpretation generation will be implemented in Phase 3.5.3.4",
    )


@router.get(
    "/cases/{case_id}/interpretation",
    response_model=GroundedCaseInterpretation,
    status_code=status.HTTP_200_OK,
    summary="Get grounded case synthesis",
)
def get_case_interpretation(case_id: str) -> GroundedCaseInterpretation:
    """Retrieve cached grounded forensic briefing and synthesis for a case.

    Strictly read-only: does not generate interpretation, invoke LLMs, or mutate cache.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Case interpretation retrieval will be implemented in Phase 3.5.3.5",
    )


@router.post(
    "/cases/{case_id}/interpretation",
    response_model=GroundedCaseInterpretation,
    status_code=status.HTTP_200_OK,
    summary="Generate or refresh grounded case synthesis",
)
def generate_case_interpretation(
    case_id: str,
    force_refresh: bool = Query(
        default=False,
        description="Whether to force regeneration and replace cache entry",
    ),
) -> GroundedCaseInterpretation:
    """Generate or refresh grounded forensic briefing and synthesis for a case."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Case interpretation generation will be implemented in Phase 3.5.3.5",
    )
