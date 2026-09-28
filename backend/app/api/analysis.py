"""
analysis.py — Analysis API router orchestrating canonical forensic recovery.
"""

from __future__ import annotations

import uuid
from typing import List
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from backend.app.models.artifact import ArtifactResponse
from backend.app.store import store
from backend.app.recovery.tracer import execute_traced_recoveries
from backend.app.recovery.adapter import (
    recovery_run_to_artifact_response,
    extract_recovered_bytes,
)


class AnalysisSummaryResponse(BaseModel):
    """Analysis execution summary response model."""

    case_id: str
    status: str = "COMPLETED"
    artifact_count: int
    artifacts: List[ArtifactResponse]


router = APIRouter(prefix="/cases", tags=["analysis"])


@router.post("/{case_id}/analyze", response_model=AnalysisSummaryResponse, status_code=status.HTTP_200_OK)
def analyze_case(case_id: str) -> AnalysisSummaryResponse:
    """Execute the canonical traced recovery engine for a case's uploaded evidence."""
    case = store.get_case(case_id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' not found",
        )

    evidence_bytes = store.get_evidence_bytes(case_id)
    if evidence_bytes is None or len(evidence_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No evidence uploaded for case '{case_id}'",
        )

    # 1. Determine evidence filename hint
    filename = case.evidence.filename if case.evidence else "evidence.img"

    # 2. Invoke Canonical Traced Recovery Engine
    runs = execute_traced_recoveries(
        filename=filename,
        content=evidence_bytes,
        case_id=case_id,
    )

    # 3. Adapt Canonical RecoveryRuns to Case Artifacts
    recovered_artifacts: List[ArtifactResponse] = []
    for run in runs:
        artifact_id = f"art_{uuid.uuid4().hex[:8]}"
        art_resp = recovery_run_to_artifact_response(
            run,
            case_id=case_id,
            artifact_id=artifact_id,
        )
        # store.add_artifact automatically establishes artifact_id -> run_id linkage via metadata["run_id"]
        store.add_artifact(art_resp)
        payload = extract_recovered_bytes(run)
        store.store_artifact_bytes(artifact_id, payload)
        recovered_artifacts.append(art_resp)

    return AnalysisSummaryResponse(
        case_id=case_id,
        status="COMPLETED",
        artifact_count=len(recovered_artifacts),
        artifacts=recovered_artifacts,
    )
