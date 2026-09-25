"""
explainer.py — AI evidence explanation generator with deterministic fallback.

Generates human-readable evidence briefs based ONLY on deterministic artifact
facts (category, status, scores, provenance, content preview). The AI explanation
is a presentation layer over deterministic facts — it never invents or recovers
evidence bytes.

Behavior:
  1. Always generates a deterministic fallback explanation from artifact facts.
  2. If an external LLM is available and configured, attempts an AI-enhanced
     explanation. On failure, returns the deterministic fallback gracefully.
  3. Explanations are cached on the artifact model (ai_summary field) for
     cache-first retrieval.
"""

from __future__ import annotations

from typing import Optional, Dict, Any, List


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
    external LLM is unavailable.

    Args:
        artifact_id: Unique artifact identifier.
        fmt: File format (e.g. "txt", "csv").
        category: Classified category.
        priority: Assigned priority level.
        status: Recovery status.
        confidence_score: Total confidence score (0–100).
        score_breakdown: 5-dimension confidence breakdown dict.
        provenance: Provenance metadata dict.
        content_preview: First ~200 bytes decoded preview (optional).

    Returns:
        Dict with 'summary' (str) and 'details' (list of str).
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
        max_val = 30 if dim == "structural_validation" else 20 if dim in ("header_validity", "footer_validity") else 15
        breakdown_parts.append(f"{label}: {val}/{max_val}")
    details.append("Score Breakdown: " + ", ".join(breakdown_parts))

    # Content preview note
    if content_preview:
        truncated = content_preview[:80].replace("\n", " ")
        if len(content_preview) > 80:
            truncated += "..."
        details.append(f'Content Preview: "{truncated}"')

    return {"summary": summary, "details": details}


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
    use_llm: bool = False,
) -> Dict[str, Any]:
    """Generate an evidence explanation, with optional LLM enhancement.

    Always produces at least the deterministic explanation. If use_llm is True
    and an LLM is configured, attempts an enhanced explanation. On any LLM
    failure, falls back to the deterministic explanation.

    Args:
        artifact_id: Unique artifact identifier.
        fmt: File format.
        category: Classified category.
        priority: Assigned priority.
        status: Recovery status.
        confidence_score: Total confidence score.
        score_breakdown: 5-dimension confidence breakdown dict.
        provenance: Provenance metadata dict.
        content_preview: Content preview string (optional).
        use_llm: Whether to attempt LLM-enhanced explanation (default False).

    Returns:
        Dict with 'summary' and 'details' keys.
    """
    # Always build deterministic explanation first as the guaranteed baseline
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

    if not use_llm:
        return deterministic

    # LLM-enhanced explanation (placeholder for Member 2 integration)
    # On failure, always return deterministic fallback
    try:
        # Future: Call external LLM API here, grounded on deterministic facts
        # For now, return deterministic as the MVP baseline
        return deterministic
    except Exception:
        # Graceful degradation: any LLM failure returns deterministic fallback
        return deterministic
