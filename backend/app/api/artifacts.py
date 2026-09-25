"""
artifacts.py — Artifacts API router for case artifact listing and detail retrieval.
"""

from __future__ import annotations

from typing import List
from fastapi import APIRouter, HTTPException, status

from backend.app.models.artifact import ArtifactResponse
from backend.app.store import store

router = APIRouter(tags=["artifacts"])


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
    return artifacts


@router.get("/artifacts/{artifact_id}", response_model=ArtifactResponse, status_code=status.HTTP_200_OK)
def get_artifact_detail(artifact_id: str) -> ArtifactResponse:
    """Retrieve details for a single recovered artifact by artifact_id."""
    artifact = store.get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact '{artifact_id}' not found",
        )
    return artifact
