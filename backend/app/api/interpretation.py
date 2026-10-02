"""
interpretation.py — API router for Grounded Evidence Interpretation.

Milestone 3.5.3.1: Router setup and response contract wiring.
Exposes canonical endpoints for artifact, cluster, and case interpretations.
Actual execution and retrieval behaviors are implemented in subsequent phases.
"""

from __future__ import annotations

import json
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status

from backend.app.models.interpretation import (
    GroundedArtifactInterpretation,
    GroundedClusterInterpretation,
    GroundedCaseInterpretation,
)
from backend.app.store import store
from backend.app.scoring.interpretation_service import get_interpretation_service

logger = logging.getLogger(__name__)

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
    artifact = store.get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact '{artifact_id}' not found",
        )

    if not artifact.ai_summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Interpretation not generated for artifact '{artifact_id}'. Call POST to generate.",
        )

    try:
        data = (
            json.loads(artifact.ai_summary)
            if isinstance(artifact.ai_summary, str)
            else artifact.ai_summary
        )
        if not isinstance(data, dict):
            raise ValueError("Persisted ai_summary is not a valid JSON dictionary")
        return GroundedArtifactInterpretation.model_validate(data).with_cached(True)
    except Exception:
        logger.error(
            f"Persisted interpretation for artifact '{artifact_id}' is malformed or invalid"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Persisted interpretation for artifact '{artifact_id}' is malformed or invalid",
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
    artifact = store.get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact '{artifact_id}' not found",
        )

    # When force_refresh=False and a valid persisted interpretation exists, reuse it without regenerating
    if not force_refresh and artifact.ai_summary:
        try:
            data = (
                json.loads(artifact.ai_summary)
                if isinstance(artifact.ai_summary, str)
                else artifact.ai_summary
            )
            if isinstance(data, dict):
                return GroundedArtifactInterpretation.model_validate(data).with_cached(True)
        except Exception:
            # If persisted data is malformed and force_refresh is False,
            # fall through to generate a valid interpretation
            pass

    try:
        service = get_interpretation_service(store)
        service._store = store
        return service.interpret_artifact(
            artifact_id=artifact_id,
            artifact=artifact,
            force_refresh=True,  # explicitly generate fresh interpretation
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate interpretation for artifact '{artifact_id}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate interpretation for artifact '{artifact_id}'",
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
