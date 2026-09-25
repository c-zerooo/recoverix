"""
artifacts.py — Artifacts API router for case artifact listing, detail retrieval,
and AI evidence explanation.
"""

from __future__ import annotations

import json
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, status

from backend.app.models.artifact import ArtifactResponse
from backend.app.store import store
from backend.app.scoring.explainer import generate_explanation

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


@router.post("/artifacts/{artifact_id}/explain", status_code=status.HTTP_200_OK)
def explain_artifact(artifact_id: str) -> Dict[str, Any]:
    """Generate or retrieve a cached AI evidence explanation for an artifact.

    Cache-first behavior:
      1. If the artifact already has a cached ai_summary, return it.
      2. Otherwise, generate a deterministic explanation from artifact facts,
         cache it on the artifact, and return it.

    The explanation is based ONLY on deterministic artifact facts (category,
    status, scores, provenance, content preview). On any failure, returns
    the deterministic fallback.
    """
    artifact = store.get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact '{artifact_id}' not found",
        )

    # Cache-first: return existing explanation if present
    if artifact.ai_summary:
        try:
            cached = json.loads(artifact.ai_summary)
            if isinstance(cached, dict) and "summary" in cached:
                return cached
        except (json.JSONDecodeError, TypeError):
            pass

    # Generate deterministic explanation from artifact facts
    score_dict = {
        "header_validity": artifact.score_breakdown.header_validity,
        "footer_validity": artifact.score_breakdown.footer_validity,
        "structural_validation": artifact.score_breakdown.structural_validation,
        "size_plausibility": artifact.score_breakdown.size_plausibility,
        "reconstruction_integrity": artifact.score_breakdown.reconstruction_integrity,
    }
    prov_dict = {
        "verified_bytes": artifact.provenance.verified_bytes,
        "reconstructed_bytes": artifact.provenance.reconstructed_bytes,
        "missing_bytes": artifact.provenance.missing_bytes,
        "reconstruction_method": artifact.provenance.reconstruction_method,
        "validation_status": artifact.provenance.validation_status,
    }

    explanation = generate_explanation(
        artifact_id=artifact_id,
        fmt=artifact.format,
        category=artifact.category or "DOCUMENT",
        priority=artifact.priority or "LOW",
        status=artifact.status,
        confidence_score=artifact.confidence_score,
        score_breakdown=score_dict,
        provenance=prov_dict,
        content_preview=artifact.content_preview,
    )

    # Cache the explanation on the artifact
    store.update_artifact(artifact_id, ai_summary=json.dumps(explanation))

    return explanation
