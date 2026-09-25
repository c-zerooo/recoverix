"""
artifacts.py — Artifacts API router for case artifact listing and detail retrieval.
"""

from __future__ import annotations

from typing import List
from fastapi import APIRouter, HTTPException, status

from backend.app.models.artifact import ArtifactResponse
from backend.app.store import store
from backend.app.scoring.explainer import explain_artifact
from typing import Dict, Any

router = APIRouter(tags=["artifacts"])


from backend.app.scoring.classifier import classify_artifact
from backend.app.scoring.priority import determine_priority
import json

def _enrich_artifact(artifact: ArtifactResponse) -> ArtifactResponse:
    # Use model_copy to avoid modifying the cached instance in the store permanently,
    # or we can modify it. We'll return a modified copy for safety.
    enriched = artifact.model_copy()
    
    if enriched.category is None:
        enriched.category = classify_artifact(enriched.format, enriched.content_preview)
    if enriched.priority is None:
        enriched.priority = determine_priority(enriched.category, enriched.content_preview, enriched.status)
    if enriched.ai_summary is None:
        explanation = explain_artifact(enriched.artifact_id, enriched)
        enriched.ai_summary = json.dumps(explanation)
        
    return enriched


@router.get("/cases/{case_id}/artifacts", response_model=List[ArtifactResponse], status_code=status.HTTP_200_OK)
def list_case_artifacts(case_id: str) -> List[ArtifactResponse]:
    """Retrieve all recovered artifacts associated with a specific case."""
    case = store.get_case(case_id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' not found",
        )

    artifacts = store.get_case_artifacts(case_id)
    if artifacts is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' not found",
        )
    return [_enrich_artifact(art) for art in artifacts]


@router.get("/artifacts/{artifact_id}", response_model=ArtifactResponse, status_code=status.HTTP_200_OK)
def get_artifact_detail(artifact_id: str) -> ArtifactResponse:
    """Retrieve details for a single recovered artifact by artifact_id."""
    artifact = store.get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact '{artifact_id}' not found",
        )
    return _enrich_artifact(artifact)


@router.post("/artifacts/{artifact_id}/explain", response_model=Dict[str, Any], status_code=status.HTTP_200_OK)
def explain_artifact_route(artifact_id: str) -> Dict[str, Any]:
    """Generate or retrieve a cached AI explanation for an artifact."""
    artifact = store.get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact '{artifact_id}' not found",
        )
    explanation = explain_artifact(artifact_id, artifact)
    
    # Store ai_summary onto artifact to populate next fetch
    # This requires mutating the stored response model directly or providing an update method.
    artifact.ai_summary = explanation
    
    return explanation
