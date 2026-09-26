"""
explainer.py — AI Evidence Explanation & Cache (Stage 11)

Generates grounded AI evidence explanations strictly from deterministic artifact facts.
Strict forensic invariant: AI NEVER generates, modifies, or invents evidence bytes,
and NEVER alters deterministic V/R/M accounting, confidence, or status.
"""

from __future__ import annotations

import os
import json
import logging
from typing import Dict, Any, Optional

from backend.app.scoring.priority import determine_priority

logger = logging.getLogger(__name__)

_explanation_cache: Dict[str, Dict[str, Any]] = {}


def _extract_facts(artifact: Any) -> Dict[str, Any]:
    """Extract deterministic evidence facts safely from any artifact/run/dict structure."""
    if isinstance(artifact, dict):
        d = artifact
    elif hasattr(artifact, "model_dump"):
        d = artifact.model_dump()
    elif hasattr(artifact, "__dict__"):
        d = artifact.__dict__
    else:
        d = {}

    fmt = str(getattr(artifact, "format", None) or d.get("format") or "unknown").lower()
    filename = str(
        getattr(artifact, "filename", None)
        or d.get("filename")
        or d.get("original_filename")
        or f"evidence.{fmt}"
    )
    status = str(getattr(artifact, "status", None) or d.get("status") or "UNRECOVERABLE")
    category = str(getattr(artifact, "category", None) or d.get("category") or "DOCUMENT")
    priority = getattr(artifact, "priority", None) or d.get("priority")

    # Confidence score
    score: Any = 0
    if hasattr(artifact, "confidence_score"):
        score = artifact.confidence_score or 0
    elif hasattr(artifact, "confidence") and isinstance(artifact.confidence, dict):
        score = artifact.confidence.get("total", 0)
    elif "confidence_score" in d:
        score = d["confidence_score"] or 0
    elif "confidence" in d and isinstance(d["confidence"], dict):
        score = d["confidence"].get("total", 0)
    try:
        if float(score).is_integer():
            score = int(score)
        else:
            score = round(float(score), 2)
    except (ValueError, TypeError):
        score = 0

    # Provenance byte counts
    if hasattr(artifact, "provenance") and artifact.provenance is not None:
        prov = artifact.provenance
        v_bytes = getattr(prov, "verified_bytes", 0)
        r_bytes = getattr(prov, "reconstructed_bytes", 0)
        m_bytes = getattr(prov, "missing_bytes", 0)
        method = getattr(prov, "reconstruction_method", "NONE")
        validation_status = getattr(
            prov, "validation_status", "PASSED" if status != "UNRECOVERABLE" else "FAILED"
        )
    else:
        v_bytes = (
            getattr(artifact, "total_verified_bytes", None)
            or d.get("verified_bytes")
            or d.get("total_verified_bytes")
            or 0
        )
        r_bytes = (
            getattr(artifact, "total_reconstructed_bytes", None)
            or d.get("reconstructed_bytes")
            or d.get("total_reconstructed_bytes")
            or 0
        )
        m_bytes = (
            getattr(artifact, "total_missing_bytes", None)
            or d.get("missing_bytes")
            or d.get("total_missing_bytes")
            or 0
        )
        method = (
            getattr(artifact, "reconstruction_method", None)
            or d.get("reconstruction_method")
            or (
                d.get("reconstruction_steps", [{}])[0].get("method")
                if d.get("reconstruction_steps")
                else "NONE"
            )
        )
        validation_status = (
            getattr(artifact, "validation_status", None)
            or d.get("validation_status")
            or ("PASSED" if status != "UNRECOVERABLE" else "FAILED")
        )

    preview = str(getattr(artifact, "content_preview", None) or d.get("content_preview") or "")

    # Assign explainable forensic priority if missing or unknown
    if not priority or priority == "Unknown":
        priority = determine_priority(category, preview, status)
        if status == "PARTIALLY_RECOVERED" and int(m_bytes) > 0 and priority != "CRITICAL":
            priority = "HIGH"
        elif status == "FULLY_RECOVERED" and priority not in ("CRITICAL", "HIGH"):
            priority = "LOW"
        elif status == "UNRECOVERABLE":
            priority = "LOW"

    return {
        "filename": filename,
        "format": fmt,
        "status": status,
        "category": category,
        "priority": str(priority),
        "confidence_score": score,
        "verified_bytes": int(v_bytes),
        "reconstructed_bytes": int(r_bytes),
        "missing_bytes": int(m_bytes),
        "reconstruction_method": str(method),
        "validation_status": str(validation_status),
        "content_preview": preview[:200],
    }


def _query_gemini_if_available(facts: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Query Gemini 1.5 Flash via REST if an API key is configured."""
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None

    try:
        import httpx

        prompt = (
            "You are the Recoverix AI Evidence Analyst, a digital forensics investigator assistant.\n"
            "Interpret ONLY the following deterministic recovery facts established by the reconstruction engine.\n"
            "CRITICAL: Do NOT invent bytes, do NOT modify bytes, do NOT override V/R/M, and do NOT contradict the status.\n\n"
            f"DETERMINISTIC FACTS:\n{json.dumps(facts, indent=2)}\n\n"
            "Return a JSON object with EXACTLY these string keys:\n"
            '- "assessment": Factual summary of verified vs reconstructed vs missing bytes.\n'
            '- "priority": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"\n'
            '- "why_it_matters": Forensic importance of the surviving structural evidence.\n'
            '- "recovery_limitation": Explicit explanation that Recoverix did not fabricate missing bytes.\n'
            '- "recommended_next_step": Concrete recommended next investigative step for examiners.\n'
        )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json"},
        }

        with httpx.Client(timeout=3.5) as client:
            resp = client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(text)
                required_keys = (
                    "assessment",
                    "priority",
                    "why_it_matters",
                    "recovery_limitation",
                    "recommended_next_step",
                )
                if all(k in parsed for k in required_keys):
                    return parsed
    except Exception as e:
        logger.warning(f"External Gemini interpretation call skipped/failed: {e}")

    return None


def explain_artifact(artifact_id: str, artifact: Any, force_refresh: bool = False) -> Dict[str, Any]:
    """Generate grounded AI evidence explanation strictly from deterministic artifact facts."""
    if not force_refresh and artifact_id in _explanation_cache:
        cached_exp = dict(_explanation_cache[artifact_id])
        cached_exp["cached"] = True
        return cached_exp

    facts = _extract_facts(artifact)

    category = facts["category"]
    priority = facts["priority"]
    status = facts["status"]
    fmt = facts["format"]
    v_bytes = facts["verified_bytes"]
    r_bytes = facts["reconstructed_bytes"]
    m_bytes = facts["missing_bytes"]
    score = facts["confidence_score"]
    method = facts["reconstruction_method"]
    validation_status = facts["validation_status"]

    # 1. Backward-compatible detail lines for Stage 11 tests & AIEvidenceBrief
    what_was_recovered = f"Recovered {v_bytes} verified bytes and {r_bytes} reconstructed bytes."
    what_is_verified = f"{v_bytes} bytes were mathematically verified."
    what_is_missing = f"{m_bytes} bytes are missing."
    status_reasoning = f"Score: {score}/100. Assigned status {status} based on deterministic rules."
    if r_bytes > 0:
        status_reasoning += " Status capped at PARTIALLY_RECOVERED because reconstructed bytes exist."
    priority_reasoning = f"Assigned {priority} based on content pattern matching and {category} categorization."

    # 2. Try external Gemini if API key is provided
    gemini_result = _query_gemini_if_available(facts)
    source = "GEMINI_1_5_FLASH" if gemini_result else "GROUNDED_ANALYST"

    if gemini_result:
        assessment = gemini_result.get("assessment", "")
        priority = gemini_result.get("priority", priority)
        why_it_matters = gemini_result.get("why_it_matters", "")
        recovery_limitation = gemini_result.get("recovery_limitation", "")
        recommended_next_step = gemini_result.get("recommended_next_step", "")
    else:
        # Grounded forensic deterministic generation
        if status == "PARTIALLY_RECOVERED":
            repair_str = f", {r_bytes} bytes were structurally repaired," if r_bytes > 0 else ""
            assessment = (
                f"This artifact is partially recoverable. {v_bytes} bytes were mathematically "
                f"verified from the uploaded evidence{repair_str} and a {m_bytes}-byte region remains unobserved."
            )
            why_it_matters = (
                f"The recovered evidence is structurally valid ({method}), but the missing "
                f"{m_bytes}-byte region prevents reconstruction of the complete artifact."
            )
            recovery_limitation = (
                f"Recoverix did not infer, synthesize, or fabricate the missing {m_bytes} bytes."
            )
            recommended_next_step = (
                "Review the original evidence source or adjacent storage regions for additional matching fragments."
            )
        elif status == "FULLY_RECOVERED":
            assessment = (
                f"This artifact is fully recovered. All {v_bytes} bytes were mathematically "
                f"verified from the uploaded evidence with 0 missing and 0 reconstructed bytes."
            )
            why_it_matters = (
                f"The artifact adheres completely to the {fmt.upper()} specification with authoritative validation. "
                "Evidence integrity is verified for judicial chain of custody."
            )
            recovery_limitation = (
                "Exact deterministic recovery. Zero heuristic AI predictions or synthetic filler bytes were used."
            )
            recommended_next_step = (
                "Export the recovered file and log the deterministic validation digest into the investigation case file."
            )
        elif status == "UNRECOVERABLE":
            assessment = (
                f"This artifact is unrecoverable under the {fmt.upper()} format specification. "
                f"{m_bytes or 'Evidence'} bytes of input yielded no valid structural markers or signatures."
            )
            why_it_matters = (
                "Severe corruption or missing critical headers prevent deterministic reconstruction. "
                "Proceeding without additional fragments would risk evidence falsification."
            )
            recovery_limitation = (
                "Recoverix strictly refused to fabricate file headers or simulate recovery on unverifiable binary streams."
            )
            recommended_next_step = (
                "Acquire adjacent unallocated disk clusters or examine raw sector dumps for overwritten carving headers."
            )
        else:
            assessment = (
                f"Artifact evaluated with status {status}. {v_bytes} verified bytes, "
                f"{r_bytes} reconstructed bytes, {m_bytes} missing bytes."
            )
            why_it_matters = f"Deterministic forensic evaluation score: {score}/100."
            recovery_limitation = "Zero heuristic AI predictions were used to generate evidence."
            recommended_next_step = "Perform manual forensic hex inspection on isolated anomaly regions."

    explanation: Dict[str, Any] = {
        "summary": f"Grounded explanation for {category} artifact.",
        "details": [
            what_was_recovered,
            what_is_verified,
            what_is_missing,
            status_reasoning,
            priority_reasoning,
        ],
        "assessment": assessment,
        "priority": priority,
        "why_it_matters": why_it_matters,
        "recovery_limitation": recovery_limitation,
        "recommended_next_step": recommended_next_step,
        "available": True,
        "cached": False,
        "source": source,
        "facts": {
            "verified_bytes": v_bytes,
            "reconstructed_bytes": r_bytes,
            "missing_bytes": m_bytes,
            "status": status,
            "format": fmt,
            "confidence_score": score,
            "reconstruction_method": method,
            "validation_status": validation_status,
        },
    }

    _explanation_cache[artifact_id] = explanation
    return explanation
