"""
explainer.py — Grounded LLM & deterministic fallback evidence explanation generator.

Generates human-readable evidence briefs based ONLY on deterministic artifact
facts (category, status, scores, provenance, content preview). The AI explanation
is a presentation layer over deterministic facts — it never invents, modifies,
or recovers evidence bytes, confidence scores, recovery status, or provenance.

Behavior:
  1. Always builds a deterministic fallback explanation from artifact facts.
  2. If LLM_ENABLED is True and an API key is available, attempts a grounded
     OpenAI-compatible Chat Completion API request.
  3. Validates the LLM JSON response schema (summary + details).
  4. On any LLM failure, timeout, network error, or invalid schema, gracefully
     falls back to the deterministic explanation.
  5. Explanations are cached on the artifact model (ai_summary field).
"""

from __future__ import annotations

import json
import os
import logging
from typing import Optional, Dict, Any, List

import httpx

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a digital evidence explanation assistant.\n\n"
    "You may only explain the deterministic forensic facts supplied to you.\n\n"
    "You must never invent evidence, missing bytes, recovered content, confidence values, "
    "validation results, provenance, classification, or priority.\n\n"
    "If bytes are missing or reconstructed, explicitly state that they are missing/reconstructed.\n\n"
    "Do not infer information that is not present in the supplied facts.\n\n"
    "Return concise investigator-facing evidence explanation.\n"
    "Respond ONLY with a JSON object matching this schema:\n"
    "{\n"
    '  "summary": "Brief executive summary sentence",\n'
    '  "details": [\n'
    '    "Detail point 1",\n'
    '    "Detail point 2"\n'
    "  ]\n"
    "}"
)


def build_deterministic_explanation(
    artifact_id: str,
    fmt: str,
    category: str,
    priority: str,
    status: str,
    confidence_score: int,
    score_breakdown: Dict[str, int],
    provenance: Dict[str, Any],
    content_preview: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a deterministic evidence explanation from artifact facts.

    This explanation is always available and requires no external services.
    It serves as both the default explanation and the fallback when an
    external LLM is unavailable or fails.
    """
    verified = provenance.get("verified_bytes", 0)
    reconstructed = provenance.get("reconstructed_bytes", 0)
    missing = provenance.get("missing_bytes", 0)
    recon_method = provenance.get("reconstruction_method", "NONE")
    val_status = provenance.get("validation_status", "UNKNOWN")

    # Build summary sentence
    status_desc = {
        "FULLY_RECOVERED": "fully recovered and validated",
        "PARTIALLY_RECOVERED": "partially recovered with some missing data",
        "CORRUPTED": "recovered but structurally corrupted",
        "UNRECOVERABLE": "unrecoverable due to severe damage",
    }
    summary = (
        f"{category.replace('_', ' ').title()} artifact ({fmt.upper()}) — "
        f"{status_desc.get(status, status.lower())}."
    )

    # Build detail lines
    details: List[str] = []

    # Recovery facts
    details.append(f"Status: {status} (Confidence Score: {confidence_score}/100)")
    details.append(f"Category: {category} | Priority: {priority}")

    # Byte accounting
    byte_parts = [f"Verified: {verified} bytes"]
    if reconstructed > 0:
        byte_parts.append(f"Reconstructed gap: {reconstructed} bytes")
    if missing > 0:
        byte_parts.append(f"Missing: {missing} bytes")
    details.append(" | ".join(byte_parts))

    # Reconstruction method
    if recon_method == "BIFRAGMENT_GAP":
        details.append(
            f"Reconstruction Method: Bounded bifragment gap reconstruction "
            f"(gap: {missing} bytes)"
        )
    elif recon_method == "NONE":
        if status == "FULLY_RECOVERED":
            details.append("Reconstruction Method: None required — contiguous recovery")
        else:
            details.append("Reconstruction Method: None applied")

    # Validation status
    details.append(f"Validation: {val_status}")

    # Score breakdown
    breakdown_parts = []
    for dim, label in [
        ("header_validity", "Header"),
        ("footer_validity", "Footer"),
        ("structural_validation", "Structure"),
        ("size_plausibility", "Size"),
        ("reconstruction_integrity", "Reconstruction"),
    ]:
        val = score_breakdown.get(dim, 0)
        max_val = (
            30
            if dim == "structural_validation"
            else 20
            if dim in ("header_validity", "footer_validity")
            else 15
        )
        breakdown_parts.append(f"{label}: {val}/{max_val}")
    details.append("Score Breakdown: " + ", ".join(breakdown_parts))

    # Content preview note
    if content_preview:
        truncated = content_preview[:80].replace("\n", " ")
        if len(content_preview) > 80:
            truncated += "..."
        details.append(f'Content Preview: "{truncated}"')

    return {"summary": summary, "details": details}


def call_llm_explanation(
    artifact_id: str,
    fmt: str,
    category: str,
    priority: str,
    status: str,
    confidence_score: int,
    score_breakdown: Dict[str, int],
    provenance: Dict[str, Any],
    content_preview: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout_seconds: float = 5.0,
) -> Optional[Dict[str, Any]]:
    """Call OpenAI-compatible Chat Completions API with deterministic facts.

    Returns validated dict {"summary": str, "details": List[str]} or None on failure.
    """
    key = api_key if api_key is not None else os.getenv("LLM_API_KEY", "")
    if not key:
        return None

    model_name = model or os.getenv("LLM_MODEL", "llama-3.2-3b-instruct")
    url_base = (base_url or os.getenv("LLM_BASE_URL", "http://127.0.0.1:8080/v1")).rstrip("/")
    endpoint = f"{url_base}/chat/completions"

    payload_facts = {
        "artifact_id": artifact_id,
        "format": fmt,
        "category": category,
        "priority": priority,
        "recovery_status": status,
        "confidence_score": confidence_score,
        "score_breakdown": score_breakdown,
        "provenance": provenance,
        "content_preview": content_preview[:200] if content_preview else None,
    }

    user_content = f"Forensic facts for artifact:\n{json.dumps(payload_facts, indent=2)}"

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    request_body = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(endpoint, headers=headers, json=request_body)
            if response.status_code != 200:
                logger.warning("LLM API returned status %s: %s", response.status_code, response.text)
                return None

            res_data = response.json()
            choices = res_data.get("choices")
            if not choices or not isinstance(choices, list):
                return None

            content_str = choices[0].get("message", {}).get("content", "")
            if not content_str:
                return None

            parsed = json.loads(content_str)
            if not isinstance(parsed, dict):
                return None

            summary = parsed.get("summary")
            details = parsed.get("details")

            if not isinstance(summary, str) or not summary.strip():
                return None
            if not isinstance(details, list) or len(details) == 0:
                return None
            if not all(isinstance(d, str) for d in details):
                return None

            return {
                "summary": summary.strip(),
                "details": [d.strip() for d in details if d.strip()],
            }
    except Exception as exc:
        logger.warning("LLM explanation request failed: %s", exc)
        return None


def generate_explanation(
    artifact_id: str,
    fmt: str,
    category: str,
    priority: str,
    status: str,
    confidence_score: int,
    score_breakdown: Dict[str, int],
    provenance: Dict[str, Any],
    content_preview: Optional[str] = None,
    use_llm: Optional[bool] = None,
) -> Dict[str, Any]:
    """Generate an evidence explanation, trying LLM if enabled with deterministic fallback.

    Args:
        artifact_id: Unique artifact identifier.
        fmt: File format.
        category: Classified category.
        priority: Assigned priority.
        status: Recovery status.
        confidence_score: Total confidence score (0–100).
        score_breakdown: 5-dimension confidence breakdown dict.
        provenance: Provenance metadata dict.
        content_preview: Content preview string (optional).
        use_llm: Explicit toggle for LLM attempt. If None, uses LLM_ENABLED env var.

    Returns:
        Dict with 'summary' (str) and 'details' (list of str) keys.
    """
    # 1. Always build deterministic explanation first as guaranteed baseline
    deterministic = build_deterministic_explanation(
        artifact_id=artifact_id,
        fmt=fmt,
        category=category,
        priority=priority,
        status=status,
        confidence_score=confidence_score,
        score_breakdown=score_breakdown,
        provenance=provenance,
        content_preview=content_preview,
    )

    # 2. Check if LLM attempt is enabled
    llm_enabled_env = os.getenv("LLM_ENABLED", "false").lower() in ("true", "1", "yes")
    should_try_llm = llm_enabled_env if use_llm is None else (use_llm and llm_enabled_env)

    if not should_try_llm:
        return deterministic

    # 3. Attempt LLM request
    llm_result = call_llm_explanation(
        artifact_id=artifact_id,
        fmt=fmt,
        category=category,
        priority=priority,
        status=status,
        confidence_score=confidence_score,
        score_breakdown=score_breakdown,
        provenance=provenance,
        content_preview=content_preview,
    )

    if llm_result is not None:
        return llm_result

    # 4. Fallback on LLM failure or missing key
    return deterministic
