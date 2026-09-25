"""
explainer.py — AI Evidence Explanation & Cache (Stage 11)
"""

from typing import Dict, Any

_explanation_cache: Dict[str, Dict[str, Any]] = {}

def explain_artifact(artifact_id: str, artifact: Any) -> Dict[str, Any]:
    """
    Generate the grounded AI evidence explanation strictly from deterministic artifact facts.
    """
    if artifact_id in _explanation_cache:
        cached_exp = dict(_explanation_cache[artifact_id])
        cached_exp["cached"] = True
        return cached_exp
        
    category = artifact.category or "Unknown"
    priority = artifact.priority or "Unknown"
    status = artifact.status
    v_bytes = artifact.provenance.verified_bytes
    r_bytes = artifact.provenance.reconstructed_bytes
    m_bytes = artifact.provenance.missing_bytes
    score = artifact.confidence_score
    
    what_was_recovered = f"Recovered {v_bytes} verified bytes and {r_bytes} reconstructed bytes."
    what_is_verified = f"{v_bytes} bytes were mathematically verified."
    what_is_missing = f"{m_bytes} bytes are missing."
    
    status_reasoning = f"Score: {score}/100. Assigned status {status} based on deterministic rules."
    if r_bytes > 0:
        status_reasoning += " Status capped at PARTIALLY_RECOVERED because reconstructed bytes exist."
        
    priority_reasoning = f"Assigned {priority} based on content pattern matching and {category} categorization."
    
    explanation = {
        "summary": f"Grounded explanation for {category} artifact.",
        "details": [
            what_was_recovered,
            what_is_verified,
            what_is_missing,
            status_reasoning,
            priority_reasoning
        ],
        "cached": False
    }
    
    _explanation_cache[artifact_id] = explanation
    return explanation
