"""
tracer.py — Deterministic execution tracer and observer for Recoverix pipelines.

Observes real recovery execution across candidate scanning, carving,
bifragment reconstruction, structural validation, and confidence scoring.
Generates structured RecoveryRun models, PipelineEvent sequence traces,
Fragment representations, DamageRegions, and ReconstructionSteps.

Does NOT modify existing recovery logic or confidence algorithms.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from dataclasses import asdict
from typing import Dict, List, Optional, Any

from backend.app.models.recovery_run import (
    RecoveryRun,
    PipelineEvent,
    Fragment,
    FragmentRelationship,
    DamageRegion,
    ReconstructionStep,
)
from backend.app.store import store
from backend.app.recovery.scanner import scan_evidence, Candidate
from backend.app.recovery.carver import carve_candidate, RecoveredArtifact
from backend.app.recovery.validators import validate_artifact, VALIDATORS
from backend.app.recovery.validators.pdf import reconstruct_pdf_xref
from backend.app.recovery.bifragment import reconstruct_bifragment
from backend.app.recovery.reconstruction import reconstruct_artifact, reconstruct_fragment_pair
from backend.app.recovery.fragment_detector import detect_text_fragments
from backend.app.recovery.relationship import select_fragment_pairs
from backend.app.scoring.confidence import evaluate_artifact_confidence
from backend.app.recovery.signatures import SYNTHETIC_START_MARKER


def execute_traced_recovery(
    filename: str,
    content: bytes,
    case_id: Optional[str] = None,
    artifact_id: Optional[str] = None,
) -> RecoveryRun:
    """Execute a traced forensic recovery run over *content*.

    Args:
        filename: Name of the evidence file.
        content: Raw evidence bytes.
        case_id: Optional associated case identifier.
        artifact_id: Optional associated artifact identifier.

    Returns:
        Stored RecoveryRun instance containing the real forensic trace.
    """
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    started_at = datetime.now(timezone.utc)

    seq = 1
    events: List[PipelineEvent] = []

    def emit_event(
        event_type: str,
        message: str,
        relevant_fragment_ids: Optional[List[str]] = None,
        relevant_artifact_info: Optional[Dict[str, Any]] = None,
    ) -> None:
        nonlocal seq
        events.append(
            PipelineEvent(
                event_id=f"evt-{seq}",
                run_id=run_id,
                sequence=seq,
                event_type=event_type,
                timestamp=datetime.now(timezone.utc),
                message=message,
                relevant_fragment_ids=relevant_fragment_ids or [],
                relevant_artifact_info=relevant_artifact_info,
            )
        )
        seq += 1

    emit_event("RECOVERY_STARTED", f"Started recovery run for '{filename}' ({len(content)} bytes)")
    emit_event("SCANNING_STARTED", f"Scanning {len(content)} bytes for format signatures")

    candidates: List[Candidate] = scan_evidence(content)

    for cand in candidates:
        emit_event(
            "FORMAT_DETECTED",
            f"Detected format signature '{cand.format}' at byte offset {cand.offset}",
            relevant_artifact_info={"format": cand.format, "offset": cand.offset},
        )
        emit_event(
            "CANDIDATE_FOUND",
            f"Candidate '{cand.candidate_id}' located at offset {cand.offset} via {cand.detection_method}",
            relevant_artifact_info={"candidate_id": cand.candidate_id, "offset": cand.offset},
        )

    fragments: List[Fragment] = []
    damage_regions: List[DamageRegion] = []
    reconstruction_steps: List[ReconstructionStep] = []

    fmt: str = "unknown"
    status_val: str = "UNRECOVERABLE"
    ver_bytes: int = 0
    rec_byte_cnt: int = 0
    miss_bytes: int = len(content)
    score_breakdown_dict: Dict[str, Any] = {}
    val_details_dict: Dict[str, Any] = {}
    prov_dict: Dict[str, Any] = {}
    output_dict: Optional[Dict[str, Any]] = None
    total_input_bytes: int = len(content)

    if candidates:
        cand = candidates[0]
        fmt = cand.format
        validator = VALIDATORS.get(fmt, lambda data: validate_artifact(fmt, data))

        # Scenario 1: Candidate with known end offset (Contiguous carved artifact)
        if cand.estimated_end_offset is not None:
            frag_len = cand.estimated_end_offset - cand.offset
            frag0 = Fragment(
                fragment_id="frag-0",
                offset=cand.offset,
                length=frag_len,
                end_offset=cand.estimated_end_offset,
                status="VERIFIED",
                source="synthetic_boundary" if cand.detection_method == "synthetic_boundary" else "magic_bytes",
                format=fmt,
                verified_bytes=frag_len,
                reconstructed_bytes=0,
                missing_bytes=0,
                validation_status="PASSED",
            )
            fragments.append(frag0)
            emit_event(
                "FRAGMENT_IDENTIFIED",
                f"Identified contiguous fragment frag-0 [{cand.offset}..{cand.estimated_end_offset}] ({frag_len} bytes)",
                relevant_fragment_ids=["frag-0"],
            )

            try:
                carved: RecoveredArtifact = carve_candidate(content, cand)
                if fmt in ("txt", "csv"):
                    emit_event("RECONSTRUCTION_STARTED", f"Attempting deterministic {fmt.upper()} format reconstruction")
                    recon_res = reconstruct_artifact(fmt, carved)
                    emit_event(
                        "RECONSTRUCTION_COMPLETED",
                        f"{fmt.upper()} reconstruction completed with status '{recon_res.status}'",
                    )
                    status_val = recon_res.status
                    ver_bytes = recon_res.verified_bytes
                    rec_byte_cnt = recon_res.reconstructed_bytes
                    miss_bytes = recon_res.missing_bytes
                    val_res = recon_res.validation_result or validator(carved)
                    val_status_str = "PASSED" if val_res.valid else "FAILED"
                    val_details_dict = asdict(val_res)
                    output_dict = {"recovered_bytes": recon_res.recovered_bytes.hex()}
                    score_breakdown_dict = {"total": recon_res.details.get("confidence_score", 100.0)}

                    for idx_m, m in enumerate(recon_res.reconstruction_methods):
                        step = ReconstructionStep(
                            step_id=f"step-{idx_m}",
                            method=m,
                            input_fragment_ids=["frag-0"],
                            gap_start=None,
                            gap_end=None,
                            gap_size=None,
                            result="SUCCESS" if recon_res.success else "FAILED",
                            verified_bytes=ver_bytes,
                            reconstructed_bytes=rec_byte_cnt,
                            missing_bytes=miss_bytes,
                            validation_status=val_status_str,
                            confidence=float(recon_res.details.get("confidence_score", 100.0)),
                        )
                        reconstruction_steps.append(step)

                    for idx_d, dmg in enumerate(recon_res.damage_regions):
                        damage_regions.append(
                            DamageRegion(
                                region_id=f"damage-{idx_d}",
                                start_offset=dmg.get("offset", 0),
                                end_offset=dmg.get("offset", 0) + dmg.get("length", 0),
                                length=dmg.get("length", 0),
                                type=dmg.get("type", "CORRUPTED"),
                                status="RECONSTRUCTED" if recon_res.success else "UNRECOVERABLE",
                                affected_fragment_ids=["frag-0"],
                            )
                        )
                        emit_event(
                            "DAMAGE_DETECTED",
                            f"Detected damage region ({dmg.get('type')}) of {dmg.get('length')} bytes at offset {dmg.get('offset')}",
                            relevant_fragment_ids=["frag-0"],
                        )
                else:
                    emit_event("VALIDATION_STARTED", f"Validating structural integrity for format '{fmt}'")
                    val_res = validator(carved)
                    val_status_str = "PASSED" if val_res.valid else "FAILED"
                    emit_event(
                        "VALIDATION_COMPLETED",
                        f"Structural validation {val_status_str}: {len(val_res.errors)} errors, {len(val_res.warnings)} warnings",
                    )

                    eval_res = evaluate_artifact_confidence(validation_result=val_res, artifact=carved)
                    emit_event(
                        "CONFIDENCE_CALCULATED",
                        f"Confidence evaluated: total={eval_res.score_breakdown.total}/100, status={eval_res.status.value}",
                    )

                    status_val = eval_res.status.value
                    ver_bytes = eval_res.provenance.verified_bytes
                    rec_byte_cnt = eval_res.provenance.reconstructed_bytes
                    miss_bytes = eval_res.provenance.missing_bytes
                    score_breakdown_dict = asdict(eval_res.score_breakdown)
                    val_details_dict = asdict(val_res)
                    prov_dict = asdict(eval_res.provenance)
                    output_dict = {"recovered_bytes": carved.recovered_bytes.hex()}

                frag0_updated = frag0.model_copy(
                    update={
                        "verified_bytes": ver_bytes,
                        "reconstructed_bytes": rec_byte_cnt,
                        "missing_bytes": miss_bytes,
                        "validation_status": val_status_str,
                    }
                )
                fragments[0] = frag0_updated
            except Exception as e:
                val_details_dict = {"error": str(e)}

        # Scenario 2: Multiple candidates without end offset (Bifragment recovery)
        elif len(candidates) >= 2:
            cand2 = candidates[1]

            raw_between = content[cand.offset:cand2.offset]
            frag_a_bytes = raw_between.rstrip(b"\x00")
            if not frag_a_bytes:
                frag_a_bytes = raw_between

            frag_a_end = cand.offset + len(frag_a_bytes)
            frag_a_len = frag_a_end - cand.offset
            gap_start = frag_a_end
            gap_end = cand2.offset
            gap_size = max(0, gap_end - gap_start)

            frag_a = Fragment(
                fragment_id="frag-0",
                offset=cand.offset,
                length=frag_a_len,
                end_offset=frag_a_end,
                status="PARTIAL",
                source="bifragment_a",
                format=fmt,
                verified_bytes=frag_a_len,
                reconstructed_bytes=0,
                missing_bytes=0,
                validation_status="PARTIAL",
            )

            frag_b_len = len(content) - cand2.offset
            frag_b = Fragment(
                fragment_id="frag-1",
                offset=cand2.offset,
                length=frag_b_len,
                end_offset=len(content),
                status="PARTIAL",
                source="bifragment_b",
                format=fmt,
                verified_bytes=frag_b_len,
                reconstructed_bytes=0,
                missing_bytes=0,
                validation_status="PARTIAL",
            )

            rel_ab = FragmentRelationship(
                source_fragment_id="frag-0",
                target_fragment_id="frag-1",
                relationship_type="BOUNDED_GAP",
                details={"gap_size": gap_size},
            )
            frag_a_rel = frag_a.model_copy(update={"relationships": [rel_ab]})
            fragments.extend([frag_a_rel, frag_b])

            emit_event(
                "FRAGMENT_IDENTIFIED",
                f"Identified bifragment frag-0 [{cand.offset}..{frag_a_end}] and frag-1 [{cand2.offset}..{len(content)}]",
                relevant_fragment_ids=["frag-0", "frag-1"],
            )

            dam0 = DamageRegion(
                region_id="damage-0",
                start_offset=gap_start,
                end_offset=gap_end,
                length=gap_size,
                type="MISSING",
                status="RECONSTRUCTABLE",
                affected_fragment_ids=["frag-0", "frag-1"],
            )
            damage_regions.append(dam0)
            emit_event(
                "DAMAGE_DETECTED",
                f"Detected missing gap of {gap_size} bytes between offset {gap_start} and {gap_end}",
                relevant_fragment_ids=["frag-0", "frag-1"],
            )

            emit_event(
                "RECONSTRUCTION_STARTED",
                f"Attempting bifragment gap reconstruction (gap size bounds: 1 to 4096)",
                relevant_fragment_ids=["frag-0", "frag-1"],
            )

            try:
                frag_b_bytes = content[cand2.offset:]
                recon_res = reconstruct_bifragment(
                    frag_a_bytes, frag_b_bytes, validator=validator, min_gap=1, max_gap=4096
                )

                rec_success = recon_res.success
                emit_event(
                    "RECONSTRUCTION_COMPLETED",
                    f"Bifragment reconstruction {'succeeded' if rec_success else 'failed'}",
                    relevant_fragment_ids=["frag-0", "frag-1"],
                )

                val_res_for_eval = recon_res.validation_result if (recon_res and recon_res.validation_result) else validator(frag_a_bytes + frag_b_bytes)
                eval_res = evaluate_artifact_confidence(
                    validation_result=val_res_for_eval,
                    reconstruction_result=recon_res,
                    actual_missing_bytes=gap_size,
                )
                emit_event(
                    "CONFIDENCE_CALCULATED",
                    f"Confidence evaluated: total={eval_res.score_breakdown.total}/100, status={eval_res.status.value}",
                )

                status_val = eval_res.status.value
                ver_bytes = eval_res.provenance.verified_bytes
                rec_byte_cnt = eval_res.provenance.reconstructed_bytes
                miss_bytes = eval_res.provenance.missing_bytes
                score_breakdown_dict = asdict(eval_res.score_breakdown)
                val_details_dict = asdict(val_res_for_eval)
                prov_dict = asdict(eval_res.provenance)
                output_bytes = (recon_res.fragment_a_bytes + recon_res.fragment_b_bytes) if (recon_res and hasattr(recon_res, "fragment_a_bytes")) else (frag_a_bytes + frag_b_bytes)
                output_dict = {"recovered_bytes": output_bytes.hex()}

                step0 = ReconstructionStep(
                    step_id="step-0",
                    method="BIFRAGMENT_GAP",
                    input_fragment_ids=["frag-0", "frag-1"],
                    gap_start=gap_start,
                    gap_end=gap_end,
                    gap_size=gap_size,
                    validated_gap_size=recon_res.gap_size if rec_success else None,
                    result="SUCCESS" if rec_success else "FAILED",
                    verified_bytes=ver_bytes,
                    reconstructed_bytes=rec_byte_cnt,
                    missing_bytes=miss_bytes,
                    validation_status="PASSED" if (recon_res.validation_result and recon_res.validation_result.valid) else "FAILED",
                    confidence=float(eval_res.score_breakdown.total),
                )
                reconstruction_steps.append(step0)

                dam0_updated = dam0.model_copy(
                    update={"status": "RECONSTRUCTED" if rec_success else "UNRECOVERABLE"}
                )
                damage_regions[0] = dam0_updated
            except Exception as e:
                val_details_dict = {"error": str(e)}

        # Scenario 3: Single candidate without end offset (e.g. PDF xref damage or raw fragment)
        else:
            raw_frag_len = len(content) - cand.offset
            frag0 = Fragment(
                fragment_id="frag-0",
                offset=cand.offset,
                length=raw_frag_len,
                end_offset=len(content),
                status="PARTIAL",
                source="magic_bytes" if cand.detection_method == "magic_bytes" else "synthetic_boundary",
                format=fmt,
                verified_bytes=raw_frag_len,
                reconstructed_bytes=0,
                missing_bytes=0,
                validation_status="UNTESTED",
            )
            fragments.append(frag0)
            emit_event(
                "FRAGMENT_IDENTIFIED",
                f"Identified candidate fragment frag-0 [{cand.offset}..{len(content)}] ({raw_frag_len} bytes)",
                relevant_fragment_ids=["frag-0"],
            )

            # Check for TXT reconstruction
            if fmt == "txt":
                raw_bytes = content[cand.offset:]
                emit_event("RECONSTRUCTION_STARTED", "Attempting deterministic TXT format reconstruction")
                recon_res = reconstruct_artifact("txt", raw_bytes)
                emit_event(
                    "RECONSTRUCTION_COMPLETED",
                    f"TXT reconstruction completed with status '{recon_res.status}'",
                )
                status_val = recon_res.status
                ver_bytes = recon_res.verified_bytes
                rec_byte_cnt = recon_res.reconstructed_bytes
                miss_bytes = recon_res.missing_bytes
                val_res = recon_res.validation_result or validator(raw_bytes)
                val_status_str = "PASSED" if val_res.valid else "FAILED"
                val_details_dict = asdict(val_res)
                output_dict = {"recovered_bytes": recon_res.recovered_bytes.hex()}
                score_breakdown_dict = {"total": recon_res.details.get("confidence_score", 100.0)}

                for idx_m, m in enumerate(recon_res.reconstruction_methods):
                    step = ReconstructionStep(
                        step_id=f"step-{idx_m}",
                        method=m,
                        input_fragment_ids=["frag-0"],
                        gap_start=None,
                        gap_end=None,
                        gap_size=None,
                        result="SUCCESS" if recon_res.success else "FAILED",
                        verified_bytes=ver_bytes,
                        reconstructed_bytes=rec_byte_cnt,
                        missing_bytes=miss_bytes,
                        validation_status=val_status_str,
                        confidence=float(recon_res.details.get("confidence_score", 100.0)),
                    )
                    reconstruction_steps.append(step)

                for idx_d, dmg in enumerate(recon_res.damage_regions):
                    damage_regions.append(
                        DamageRegion(
                            region_id=f"damage-{idx_d}",
                            start_offset=dmg.get("offset", 0),
                            end_offset=dmg.get("offset", 0) + dmg.get("length", 0),
                            length=dmg.get("length", 0),
                            type=dmg.get("type", "CORRUPTED"),
                            status="RECONSTRUCTED" if recon_res.success else "UNRECOVERABLE",
                            affected_fragment_ids=["frag-0"],
                        )
                    )
                    emit_event(
                        "DAMAGE_DETECTED",
                        f"Detected damage region ({dmg.get('type')}) of {dmg.get('length')} bytes at offset {dmg.get('offset')}",
                        relevant_fragment_ids=["frag-0"],
                    )

            # Check for PDF xref reconstruction potential
            elif fmt == "pdf":
                raw_bytes = content[cand.offset:]
                val_initial = validator(raw_bytes)

                if not val_initial.valid and b"xref" not in raw_bytes or any("xref" in e.lower() for e in val_initial.errors):
                    emit_event(
                        "DAMAGE_DETECTED",
                        "Detected damaged or missing PDF cross-reference table (xref)",
                        relevant_fragment_ids=["frag-0"],
                    )
                    dam0 = DamageRegion(
                        region_id="damage-0",
                        start_offset=cand.offset,
                        end_offset=len(content),
                        length=raw_frag_len,
                        type="CORRUPTED",
                        status="RECONSTRUCTABLE",
                        affected_fragment_ids=["frag-0"],
                    )
                    damage_regions.append(dam0)

                    emit_event(
                        "RECONSTRUCTION_STARTED",
                        "Attempting deterministic PDF cross-reference (xref) reconstruction",
                        relevant_fragment_ids=["frag-0"],
                    )

                    rebuilt_bytes, xref_ok = reconstruct_pdf_xref(raw_bytes)
                    emit_event(
                        "RECONSTRUCTION_COMPLETED",
                        f"PDF xref reconstruction {'succeeded' if xref_ok else 'failed'}",
                        relevant_fragment_ids=["frag-0"],
                    )

                    if xref_ok:
                        carved_rebuilt = RecoveredArtifact(
                            candidate_id="cand-0",
                            format="pdf",
                            mime_type="application/pdf",
                            category="document",
                            source_offset=cand.offset,
                            recovered_bytes=rebuilt_bytes,
                            recovered_byte_count=len(rebuilt_bytes),
                            carving_method="XREF_RECONSTRUCTED",
                        )
                        val_res = validator(carved_rebuilt)
                        eval_res = evaluate_artifact_confidence(validation_result=val_res, artifact=carved_rebuilt)

                        status_val = eval_res.status.value
                        ver_bytes = eval_res.provenance.verified_bytes
                        rec_byte_cnt = eval_res.provenance.reconstructed_bytes
                        miss_bytes = eval_res.provenance.missing_bytes
                        score_breakdown_dict = asdict(eval_res.score_breakdown)
                        val_details_dict = asdict(val_res)
                        prov_dict = asdict(eval_res.provenance)
                        output_dict = {"recovered_bytes": rebuilt_bytes.hex()}

                        step0 = ReconstructionStep(
                            step_id="step-0",
                            method="XREF_RECONSTRUCTION",
                            input_fragment_ids=["frag-0"],
                            gap_start=None,
                            gap_end=None,
                            gap_size=None,
                            result="SUCCESS",
                            verified_bytes=ver_bytes,
                            reconstructed_bytes=rec_byte_cnt,
                            validation_status="PASSED" if val_res.valid else "FAILED",
                            confidence=float(eval_res.score_breakdown.total),
                        )
                        reconstruction_steps.append(step0)
                        damage_regions[0] = dam0.model_copy(update={"status": "RECONSTRUCTED"})
                    else:
                        val_res = val_initial
                        eval_res = evaluate_artifact_confidence(val_res)
                        status_val = eval_res.status.value
                        ver_bytes = eval_res.provenance.verified_bytes
                        rec_byte_cnt = eval_res.provenance.reconstructed_bytes
                        miss_bytes = eval_res.provenance.missing_bytes
                        score_breakdown_dict = asdict(eval_res.score_breakdown)
                        val_details_dict = asdict(val_res)
                        prov_dict = asdict(eval_res.provenance)
                        output_dict = {"recovered_bytes": raw_bytes.hex()}

            if not reconstruction_steps:
                try:
                    raw_frag = content[cand.offset:]
                    emit_event("VALIDATION_STARTED", f"Validating format '{fmt}' on raw fragment")
                    val_res = validator(raw_frag)
                    val_status_str = "PASSED" if val_res.valid else "FAILED"
                    emit_event("VALIDATION_COMPLETED", f"Validation {val_status_str}")

                    eval_res = evaluate_artifact_confidence(val_res, artifact=raw_frag)
                    emit_event(
                        "CONFIDENCE_CALCULATED",
                        f"Confidence evaluated: total={eval_res.score_breakdown.total}/100, status={eval_res.status.value}",
                    )

                    status_val = eval_res.status.value
                    ver_bytes = eval_res.provenance.verified_bytes
                    rec_byte_cnt = eval_res.provenance.reconstructed_bytes
                    miss_bytes = eval_res.provenance.missing_bytes
                    score_breakdown_dict = asdict(eval_res.score_breakdown)
                    val_details_dict = asdict(val_res)
                    prov_dict = asdict(eval_res.provenance)
                    output_dict = {"recovered_bytes": raw_frag.hex()}
                except Exception as e:
                    val_details_dict = {"error": str(e)}

    # Scenario 3b: No signature candidates, but the evidence is TXT/CSV.
    # Runs deterministic fragment detection, fragment relationship identification,
    # and bounded-gap reconstruction. Operates on evidence bytes only.
    elif filename.rsplit(".", 1)[-1].lower() in ("txt", "csv"):
        target_fmt = filename.rsplit(".", 1)[-1].lower()

        emit_event(
            "FRAGMENT_DETECTION_STARTED",
            f"Scanning {len(content)} bytes for {target_fmt.upper()} text fragments",
        )
        detected = detect_text_fragments(content, target_fmt)
        emit_event(
            "FRAGMENT_DETECTION_COMPLETED",
            f"Detected {len(detected)} {target_fmt.upper()} fragment(s) from evidence structure",
            relevant_fragment_ids=[f.fragment_id for f in detected],
        )

        for frag in detected:
            emit_event(
                "FRAGMENT_IDENTIFIED",
                f"Identified {frag.fragment_id} [{frag.offset}..{frag.end_offset}] "
                f"({frag.length} bytes, {frag.line_count} lines)",
                relevant_fragment_ids=[frag.fragment_id],
            )

        if not detected:
            status_val = "UNRECOVERABLE"
            fmt = target_fmt
            ver_bytes = 0
            rec_byte_cnt = 0
            miss_bytes = len(content)
            val_details_dict = {"error": "No text-structured fragment detected"}
            prov_dict = {
                "verified_bytes": 0,
                "reconstructed_bytes": 0,
                "missing_bytes": len(content),
            }
            damage_regions.append(
                DamageRegion(
                    region_id="damage-0",
                    start_offset=0,
                    end_offset=len(content),
                    length=len(content),
                    type="UNRECOVERABLE",
                    status="UNRECOVERABLE",
                    affected_fragment_ids=[],
                )
            )
            emit_event(
                "DAMAGE_DETECTED",
                f"No recoverable text structure in {len(content)} bytes of evidence",
            )
        else:
            fmt = target_fmt
            pairs = select_fragment_pairs(detected)
            fragment_objs = []
            for frag in detected:
                fragment_objs.append(
                    Fragment(
                        fragment_id=frag.fragment_id,
                        offset=frag.offset,
                        length=frag.length,
                        end_offset=frag.end_offset,
                        status="VERIFIED",
                        source="text_structure",
                        format=target_fmt,
                        verified_bytes=frag.length,
                        reconstructed_bytes=0,
                        missing_bytes=0,
                        validation_status="PASSED",
                    )
                )
            fragments.extend(fragment_objs)

            if pairs:
                frag_a, frag_b, rel = pairs[0]
                emit_event(
                    "FRAGMENT_RELATIONSHIP_IDENTIFIED",
                    f"{rel.relationship_type}: {rel.fragment_a_id} + unknown gap + "
                    f"{rel.fragment_b_id} (observed gap {rel.observed_gap} bytes)",
                    relevant_fragment_ids=[rel.fragment_a_id, rel.fragment_b_id],
                )
                for obj in fragments:
                    if obj.fragment_id == rel.fragment_b_id:
                        obj.relationships.append(
                            FragmentRelationship(
                                source_fragment_id=rel.fragment_a_id,
                                target_fragment_id=rel.fragment_b_id,
                                relationship_type="BOUNDED_GAP",
                                details={
                                    "observed_gap": rel.observed_gap,
                                    "signals": rel.signals,
                                },
                            )
                        )

                emit_event(
                    "RECONSTRUCTION_STARTED",
                    f"Bounded gap search for {target_fmt.upper()} in range [1, 4096]",
                    relevant_fragment_ids=[rel.fragment_a_id, rel.fragment_b_id],
                )
                recon_res = reconstruct_fragment_pair(
                    target_fmt, frag_a.data, frag_b.data, observed_gap=rel.observed_gap
                )
                emit_event(
                    "RECONSTRUCTION_COMPLETED",
                    f"{target_fmt.upper()} fragment reconstruction status "
                    f"'{recon_res.status}': {recon_res.details['notice']}",
                    relevant_fragment_ids=[rel.fragment_a_id, rel.fragment_b_id],
                )

                status_val = recon_res.status
                ver_bytes = recon_res.verified_bytes
                rec_byte_cnt = recon_res.reconstructed_bytes
                miss_bytes = recon_res.missing_bytes
                val_res = recon_res.validation_result
                val_details_dict = asdict(val_res) if val_res else {}
                score_breakdown_dict = {
                    "total": float(
                        (val_res.details or {}).get("confidence_score", 100.0)
                        if val_res
                        else 0.0
                    )
                }
                prov_dict = {
                    "verified_bytes": ver_bytes,
                    "reconstructed_bytes": rec_byte_cnt,
                    "missing_bytes": miss_bytes,
                    "attributed_input_bytes": recon_res.details.get(
                        "fragment_input_bytes", frag_a.length + frag_b.length
                    ),
                    **recon_res.details,
                }
                output_dict = {"recovered_bytes": recon_res.recovered_bytes.hex()}

                reconstruction_steps.append(
                    ReconstructionStep(
                        step_id="step-0",
                        method="BIFRAGMENT_GAP",
                        input_fragment_ids=[rel.fragment_a_id, rel.fragment_b_id],
                        gap_start=frag_a.end_offset,
                        gap_end=frag_b.offset,
                        gap_size=rel.observed_gap,
                        validated_gap_size=recon_res.details.get("selected_gap_size"),
                        result="SUCCESS" if recon_res.success else "FAILED",
                        verified_bytes=ver_bytes,
                        reconstructed_bytes=rec_byte_cnt,
                        missing_bytes=miss_bytes,
                        validation_status="PASSED" if val_res and val_res.valid else "FAILED",
                        confidence=score_breakdown_dict["total"],
                    )
                )
                damage_regions.append(
                    DamageRegion(
                        region_id="damage-0",
                        start_offset=frag_a.end_offset,
                        end_offset=frag_b.offset,
                        length=rel.observed_gap,
                        type="MISSING",
                        status="UNRECOVERABLE",
                        affected_fragment_ids=[rel.fragment_a_id, rel.fragment_b_id],
                    )
                )
                emit_event(
                    "DAMAGE_DETECTED",
                    f"Confirmed physically missing region of {rel.observed_gap} bytes "
                    f"between offset {frag_a.end_offset} and {frag_b.offset}",
                    relevant_fragment_ids=[rel.fragment_a_id, rel.fragment_b_id],
                )
            else:
                # Single detected fragment: no seam is provable from the evidence,
                # so no gap is claimed. Reconstruct the surviving text honestly.
                recon_res = reconstruct_artifact(target_fmt, detected[0].data)
                emit_event(
                    "RECONSTRUCTION_COMPLETED",
                    f"{target_fmt.upper()} single-fragment reconstruction status "
                    f"'{recon_res.status}'",
                    relevant_fragment_ids=[detected[0].fragment_id],
                )
                status_val = recon_res.status
                ver_bytes = recon_res.verified_bytes
                rec_byte_cnt = recon_res.reconstructed_bytes
                miss_bytes = recon_res.missing_bytes
                val_res = recon_res.validation_result
                val_details_dict = asdict(val_res) if val_res else {}
                score_breakdown_dict = {
                    "total": float(recon_res.details.get("confidence_score", 100.0))
                }
                prov_dict = {
                    "verified_bytes": ver_bytes,
                    "reconstructed_bytes": rec_byte_cnt,
                    "missing_bytes": miss_bytes,
                    "attributed_input_bytes": len(detected[0].data),
                }
                output_dict = {"recovered_bytes": recon_res.recovered_bytes.hex()}
                # "NONE" is the sentinel meaning "no reconstruction was required".
                # An intact file must not acquire a fake reconstruction step.
                actual_methods = [
                    m for m in recon_res.reconstruction_methods if m != "NONE"
                ]
                for idx_m, m in enumerate(actual_methods):
                    reconstruction_steps.append(
                        ReconstructionStep(
                            step_id=f"step-{idx_m}",
                            method=m,
                            input_fragment_ids=[detected[0].fragment_id],
                            result="SUCCESS" if recon_res.success else "FAILED",
                            verified_bytes=ver_bytes,
                            reconstructed_bytes=rec_byte_cnt,
                            missing_bytes=miss_bytes,
                            validation_status="PASSED" if val_res and val_res.valid else "FAILED",
                            confidence=score_breakdown_dict["total"],
                        )
                    )
                for idx_d, dmg in enumerate(recon_res.damage_regions):
                    damage_regions.append(
                        DamageRegion(
                            region_id=f"damage-{idx_d}",
                            start_offset=dmg.get("offset", 0),
                            end_offset=dmg.get("offset", 0) + dmg.get("length", 0),
                            length=dmg.get("length", 0),
                            type=dmg.get("type", "CORRUPTED"),
                            status="RECONSTRUCTED" if recon_res.success else "UNRECOVERABLE",
                            affected_fragment_ids=[detected[0].fragment_id],
                        )
                    )

            # Accounting base is the artifact byte budget: verified + reconstructed
            # + missing. When a joinable pair was found, the bytes between the two
            # fragments are non-artifact separator data and are excluded from the
            # artifact budget (they are the spatial separation that bounds the
            # missing region, not artifact bytes). With a single fragment there is
            # no such separator, so any evidence byte outside it is unattributed
            # artifact data and is reported missing rather than claimed recovered.
            attributed_input = int(prov_dict.get("attributed_input_bytes", 0) or 0)
            if pairs:
                separator = max(0, len(content) - attributed_input)
                prov_dict["inter_fragment_separator_bytes"] = separator
                prov_dict["unattributed_evidence_bytes"] = 0
            else:
                unattributed = max(0, len(content) - attributed_input)
                prov_dict["unattributed_evidence_bytes"] = unattributed
                if unattributed:
                    miss_bytes += unattributed
                    if status_val == "FULLY_RECOVERED":
                        status_val = "PARTIALLY_RECOVERED"
                    emit_event(
                        "DAMAGE_DETECTED",
                        f"{unattributed} evidence byte(s) fall outside every detected "
                        "text fragment and are reported as missing, not recovered",
                    )
            prov_dict["evidence_size"] = len(content)
            prov_dict["missing_bytes"] = miss_bytes
            total_input_bytes = ver_bytes + rec_byte_cnt + miss_bytes

            # Structural validity alone must not yield full confidence. Scale it by
            # the fraction of the artifact budget that is actually accounted for, so
            # a file missing most of its bytes can never report near-100% confidence.
            if total_input_bytes:
                coverage = (ver_bytes + rec_byte_cnt) / total_input_bytes
                score_breakdown_dict = {
                    **score_breakdown_dict,
                    "total": round(
                        float(score_breakdown_dict.get("total", 0.0)) * coverage, 2
                    ),
                    "structural_score": score_breakdown_dict.get("total"),
                    "byte_coverage": round(coverage, 6),
                }

    # Scenario 4: No candidate signatures found (direct format validation or unrecoverable)
    else:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
        target_fmt = ext if ext in VALIDATORS else "txt"

        emit_event("VALIDATION_STARTED", f"Testing direct format validation for '{target_fmt}'")
        val_res = validate_artifact(target_fmt, content)

        if val_res.valid:
            fmt = target_fmt
            emit_event("VALIDATION_COMPLETED", f"Direct validation passed for '{fmt}'")
            eval_res = evaluate_artifact_confidence(val_res, artifact=content)
            emit_event(
                "CONFIDENCE_CALCULATED",
                f"Confidence evaluated: total={eval_res.score_breakdown.total}/100, status={eval_res.status.value}",
            )

            status_val = eval_res.status.value
            ver_bytes = len(content)
            rec_byte_cnt = 0
            miss_bytes = 0
            score_breakdown_dict = asdict(eval_res.score_breakdown)
            val_details_dict = asdict(val_res)
            prov_dict = asdict(eval_res.provenance)
            output_dict = {"recovered_bytes": content.hex()}

            frag0 = Fragment(
                fragment_id="frag-0",
                offset=0,
                length=len(content),
                end_offset=len(content),
                status="VERIFIED",
                source="direct_validation",
                format=fmt,
                verified_bytes=ver_bytes,
                reconstructed_bytes=0,
                missing_bytes=0,
                validation_status="PASSED",
            )
            fragments.append(frag0)
        elif target_fmt == "txt" or ext == "txt":
            recon_res = reconstruct_artifact("txt", content)
            if recon_res.success:
                fmt = "txt"
                emit_event("RECONSTRUCTION_STARTED", "Attempting deterministic TXT format reconstruction on raw file")
                emit_event("RECONSTRUCTION_COMPLETED", f"TXT reconstruction completed with status '{recon_res.status}'")
                status_val = recon_res.status
                ver_bytes = recon_res.verified_bytes
                rec_byte_cnt = recon_res.reconstructed_bytes
                miss_bytes = recon_res.missing_bytes
                val_res = recon_res.validation_result or validate_artifact("txt", recon_res.recovered_bytes)
                val_status_str = "PASSED" if val_res.valid else "FAILED"
                val_details_dict = asdict(val_res)
                output_dict = {"recovered_bytes": recon_res.recovered_bytes.hex()}
                score_breakdown_dict = {"total": recon_res.details.get("confidence_score", 100.0)}

                frag0 = Fragment(
                    fragment_id="frag-0",
                    offset=0,
                    length=len(content),
                    end_offset=len(content),
                    status="PARTIAL",
                    source="direct_reconstruction",
                    format="txt",
                    verified_bytes=ver_bytes,
                    reconstructed_bytes=rec_byte_cnt,
                    missing_bytes=miss_bytes,
                    validation_status=val_status_str,
                )
                fragments.append(frag0)

                for idx_m, m in enumerate(recon_res.reconstruction_methods):
                    step = ReconstructionStep(
                        step_id=f"step-{idx_m}",
                        method=m,
                        input_fragment_ids=["frag-0"],
                        gap_start=None,
                        gap_end=None,
                        gap_size=None,
                        result="SUCCESS" if recon_res.success else "FAILED",
                        verified_bytes=ver_bytes,
                        reconstructed_bytes=rec_byte_cnt,
                        missing_bytes=miss_bytes,
                        validation_status=val_status_str,
                        confidence=float(recon_res.details.get("confidence_score", 100.0)),
                    )
                    reconstruction_steps.append(step)

                for idx_d, dmg in enumerate(recon_res.damage_regions):
                    damage_regions.append(
                        DamageRegion(
                            region_id=f"damage-{idx_d}",
                            start_offset=dmg.get("offset", 0),
                            end_offset=dmg.get("offset", 0) + dmg.get("length", 0),
                            length=dmg.get("length", 0),
                            type=dmg.get("type", "CORRUPTED"),
                            status="RECONSTRUCTED" if recon_res.success else "UNRECOVERABLE",
                            affected_fragment_ids=["frag-0"],
                        )
                    )
            else:
                fmt = ext
                status_val = "UNRECOVERABLE"
                val_details_dict = {"error": "TXT reconstruction failed"}
                # The evidence is not recoverable text. Record the whole buffer as
                # an unrecoverable damage region rather than returning a bare
                # status with no record of why.
                ver_bytes = 0
                rec_byte_cnt = 0
                miss_bytes = len(content)
                damage_regions.append(
                    DamageRegion(
                        region_id="damage-0",
                        start_offset=0,
                        end_offset=len(content),
                        length=len(content),
                        type="BINARY_GARBAGE",
                        status="UNRECOVERABLE",
                        details="Evidence yielded no recoverable text content",
                        affected_fragment_ids=["frag-0"],
                    )
                )
                total_input_bytes = len(content)
        else:
            # Test other format validators
            matched_fmt = None
            for test_fmt in ["json", "xml", "png", "jpeg", "csv", "txt"]:
                val_test = validate_artifact(test_fmt, content)
                if val_test.valid:
                    matched_fmt = test_fmt
                    val_res = val_test
                    break

            if matched_fmt:
                fmt = matched_fmt
                emit_event("VALIDATION_COMPLETED", f"Direct validation passed for format '{fmt}'")
                eval_res = evaluate_artifact_confidence(val_res, artifact=content)
                emit_event(
                    "CONFIDENCE_CALCULATED",
                    f"Confidence evaluated: total={eval_res.score_breakdown.total}/100, status={eval_res.status.value}",
                )

                status_val = eval_res.status.value
                ver_bytes = len(content)
                rec_byte_cnt = len(content)
                miss_bytes = 0
                score_breakdown_dict = asdict(eval_res.score_breakdown)
                val_details_dict = asdict(val_res)
                prov_dict = asdict(eval_res.provenance)
                output_dict = {"recovered_bytes": content.hex()}

                frag0 = Fragment(
                    fragment_id="frag-0",
                    offset=0,
                    length=len(content),
                    end_offset=len(content),
                    status="VERIFIED",
                    source="direct_validation",
                    format=fmt,
                    verified_bytes=ver_bytes,
                    reconstructed_bytes=0,
                    missing_bytes=0,
                    validation_status="PASSED",
                )
                fragments.append(frag0)
            else:
                fmt = ext
                status_val = "UNRECOVERABLE"
                emit_event("VALIDATION_COMPLETED", "Direct validation failed across all formats")

                eval_res = evaluate_artifact_confidence(val_res)
                emit_event(
                    "CONFIDENCE_CALCULATED",
                    f"Confidence evaluated: total={eval_res.score_breakdown.total}/100, status={eval_res.status.value}",
                )

                score_breakdown_dict = asdict(eval_res.score_breakdown)
                val_details_dict = asdict(val_res)
                prov_dict = asdict(eval_res.provenance)
                ver_bytes = 0
                rec_byte_cnt = 0
                miss_bytes = len(content)

                dam0 = DamageRegion(
                    region_id="damage-0",
                    start_offset=0,
                    end_offset=len(content),
                    length=len(content),
                    type="CORRUPTED",
                    status="UNRECOVERABLE",
                    affected_fragment_ids=[],
                )
                damage_regions.append(dam0)
                emit_event(
                    "DAMAGE_DETECTED",
                    f"Entire evidence buffer of {len(content)} bytes is severely corrupt/unrecoverable",
                )

    emit_event("RECOVERY_COMPLETED", f"Recovery run completed with status '{status_val}'")

    completed_at = datetime.now(timezone.utc)

    run = RecoveryRun(
        run_id=run_id,
        artifact_id=artifact_id,
        filename=filename,
        format=fmt,
        status=status_val,
        started_at=started_at,
        completed_at=completed_at,
        total_input_bytes=total_input_bytes,
        total_verified_bytes=ver_bytes,
        total_reconstructed_bytes=rec_byte_cnt,
        total_missing_bytes=miss_bytes,
        fragments=fragments,
        damage_regions=damage_regions,
        reconstruction_steps=reconstruction_steps,
        events=events,
        validation=val_details_dict,
        confidence=score_breakdown_dict,
        provenance=prov_dict,
        output=output_dict,
    )

    store.add_recovery_run(run)
    return run
