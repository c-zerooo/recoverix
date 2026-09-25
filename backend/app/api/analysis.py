"""
analysis.py — Analysis API router orchestrating deterministic Tasks 1–7 recovery pipeline.
"""

from __future__ import annotations

import uuid
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from backend.app.models.artifact import (
    ArtifactResponse,
    ConfidenceBreakdownSchema,
    ArtifactProvenanceSchema,
)
from backend.app.store import store
from backend.app.recovery.scanner import scan_evidence, Candidate
from backend.app.recovery.carver import carve_candidate, RecoveredArtifact
from backend.app.recovery.validators import validate_txt, validate_csv
from backend.app.recovery.bifragment import reconstruct_bifragment
from backend.app.scoring.confidence import evaluate_artifact_confidence


class AnalysisSummaryResponse(BaseModel):
    """Analysis execution summary response model."""

    case_id: str
    status: str = "COMPLETED"
    artifact_count: int
    artifacts: List[ArtifactResponse]


router = APIRouter(prefix="/cases", tags=["analysis"])


@router.post("/{case_id}/analyze", response_model=AnalysisSummaryResponse, status_code=status.HTTP_200_OK)
def analyze_case(case_id: str) -> AnalysisSummaryResponse:
    """Execute the deterministic recovery pipeline for a case's uploaded evidence."""
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

    # 1. Scanner Layer (Task 3)
    candidates: List[Candidate] = scan_evidence(evidence_bytes)
    recovered_artifacts: List[ArtifactResponse] = []

    # 2. Process Candidates (Task 4 Carver, Task 5 Validator, Task 6 Bifragment, Task 7 Scoring)
    processed_candidates = set()

    for idx, candidate in enumerate(candidates):
        if candidate.candidate_id in processed_candidates:
            continue

        # Select validator function
        validator = validate_txt if candidate.format == "txt" else validate_csv

        if candidate.estimated_end_offset is not None:
            # Contiguous Artifact Carving (Task 4)
            carved_artifact: RecoveredArtifact = carve_candidate(evidence_bytes, candidate)
            val_res = validator(carved_artifact)
            eval_res = evaluate_artifact_confidence(validation_result=val_res, artifact=carved_artifact)

            preview = None
            if carved_artifact.recovered_bytes:
                preview = carved_artifact.recovered_bytes[:200].decode("utf-8", errors="replace")

            art_resp = ArtifactResponse(
                artifact_id=f"art_{uuid.uuid4().hex[:8]}",
                case_id=case_id,
                format=carved_artifact.format,
                size_bytes=carved_artifact.recovered_byte_count,
                confidence_score=eval_res.score_breakdown.total,
                score_breakdown=ConfidenceBreakdownSchema(
                    header_validity=eval_res.score_breakdown.header_validity,
                    footer_validity=eval_res.score_breakdown.footer_validity,
                    structural_validation=eval_res.score_breakdown.structural_validation,
                    size_plausibility=eval_res.score_breakdown.size_plausibility,
                    reconstruction_integrity=eval_res.score_breakdown.reconstruction_integrity,
                    total=eval_res.score_breakdown.total,
                ),
                status=eval_res.status.value,
                provenance=ArtifactProvenanceSchema(
                    verified_bytes=eval_res.provenance.verified_bytes,
                    reconstructed_bytes=eval_res.provenance.reconstructed_bytes,
                    missing_bytes=eval_res.provenance.missing_bytes,
                    reconstruction_method=eval_res.provenance.reconstruction_method,
                    validation_status=eval_res.provenance.validation_status,
                ),
                category=None,
                priority=None,
                ai_summary=None,
                content_preview=preview,
                metadata={
                    "offset": carved_artifact.source_offset,
                    "carving_method": carved_artifact.carving_method,
                    "candidate_id": candidate.candidate_id,
                },
            )
            store.add_artifact(art_resp)
            store.store_artifact_bytes(art_resp.artifact_id, carved_artifact.recovered_bytes)
            recovered_artifacts.append(art_resp)
            processed_candidates.add(candidate.candidate_id)

        else:
            # Truncated or fragmented candidate without estimated end offset (Task 6 Bifragment)
            # Attempt bifragment reconstruction if another candidate exists
            bifragment_success = False

            for other_cand in candidates:
                if other_cand.candidate_id == candidate.candidate_id:
                    continue
                if other_cand.format != candidate.format:
                    continue

                # Attempt bifragment reconstruction
                frag_a = evidence_bytes[candidate.offset:candidate.offset + 200]
                frag_b = evidence_bytes[other_cand.offset:]

                recon_res = reconstruct_bifragment(
                    frag_a, frag_b, validator=validator, min_gap=1, max_gap=4096
                )

                if recon_res.success:
                    eval_res = evaluate_artifact_confidence(
                        validation_result=recon_res.validation_result,
                        reconstruction_result=recon_res,
                    )

                    art_resp = ArtifactResponse(
                        artifact_id=f"art_{uuid.uuid4().hex[:8]}",
                        case_id=case_id,
                        format=recon_res.format,
                        size_bytes=len(recon_res.fragment_a_bytes) + len(recon_res.fragment_b_bytes),
                        confidence_score=eval_res.score_breakdown.total,
                        score_breakdown=ConfidenceBreakdownSchema(
                            header_validity=eval_res.score_breakdown.header_validity,
                            footer_validity=eval_res.score_breakdown.footer_validity,
                            structural_validation=eval_res.score_breakdown.structural_validation,
                            size_plausibility=eval_res.score_breakdown.size_plausibility,
                            reconstruction_integrity=eval_res.score_breakdown.reconstruction_integrity,
                            total=eval_res.score_breakdown.total,
                        ),
                        status=eval_res.status.value,
                        provenance=ArtifactProvenanceSchema(
                            verified_bytes=eval_res.provenance.verified_bytes,
                            reconstructed_bytes=eval_res.provenance.reconstructed_bytes,
                            missing_bytes=eval_res.provenance.missing_bytes,
                            reconstruction_method=eval_res.provenance.reconstruction_method,
                            validation_status=eval_res.provenance.validation_status,
                        ),
                        category=None,
                        priority=None,
                        ai_summary=None,
                        content_preview=None,
                        metadata={
                            "reconstruction_method": recon_res.reconstruction_method,
                            "gap_size": recon_res.gap_size,
                            "fragment_a_id": candidate.candidate_id,
                            "fragment_b_id": other_cand.candidate_id,
                        },
                    )
                    store.add_artifact(art_resp)
                    recon_bytes = recon_res.fragment_a_bytes + recon_res.fragment_b_bytes
                    store.store_artifact_bytes(art_resp.artifact_id, recon_bytes)
                    recovered_artifacts.append(art_resp)
                    processed_candidates.add(candidate.candidate_id)
                    processed_candidates.add(other_cand.candidate_id)
                    bifragment_success = True
                    break

            if not bifragment_success:
                # Carve available bytes up to evidence end or end marker
                raw_frag = evidence_bytes[candidate.offset:]
                val_res = validator(raw_frag)
                eval_res = evaluate_artifact_confidence(validation_result=val_res, artifact=raw_frag)

                art_resp = ArtifactResponse(
                    artifact_id=f"art_{uuid.uuid4().hex[:8]}",
                    case_id=case_id,
                    format=candidate.format,
                    size_bytes=len(raw_frag),
                    confidence_score=eval_res.score_breakdown.total,
                    score_breakdown=ConfidenceBreakdownSchema(
                        header_validity=eval_res.score_breakdown.header_validity,
                        footer_validity=eval_res.score_breakdown.footer_validity,
                        structural_validation=eval_res.score_breakdown.structural_validation,
                        size_plausibility=eval_res.score_breakdown.size_plausibility,
                        reconstruction_integrity=eval_res.score_breakdown.reconstruction_integrity,
                        total=eval_res.score_breakdown.total,
                    ),
                    status=eval_res.status.value,
                    provenance=ArtifactProvenanceSchema(
                        verified_bytes=eval_res.provenance.verified_bytes,
                        reconstructed_bytes=eval_res.provenance.reconstructed_bytes,
                        missing_bytes=eval_res.provenance.missing_bytes,
                        reconstruction_method=eval_res.provenance.reconstruction_method,
                        validation_status=eval_res.provenance.validation_status,
                    ),
                    category=None,
                    priority=None,
                    ai_summary=None,
                    content_preview=raw_frag[:200].decode("utf-8", errors="replace"),
                    metadata={
                        "offset": candidate.offset,
                        "candidate_id": candidate.candidate_id,
                    },
                )
                store.add_artifact(art_resp)
                recovered_artifacts.append(art_resp)
                processed_candidates.add(candidate.candidate_id)

    return AnalysisSummaryResponse(
        case_id=case_id,
        status="COMPLETED",
        artifact_count=len(recovered_artifacts),
        artifacts=recovered_artifacts,
    )
