"""
priority.py — Deterministic artifact priority assignment.

Assigns priority levels based on artifact category, content preview, and
recovery status. AI never overrides deterministic priority assignments.

Priority Levels:
  - CRITICAL: Privileged execution evidence, credentials, private keys.
  - HIGH: Financial data, photo/media evidence, database records with sensitive content.
  - MEDIUM: System traces, documents with suspicious content.
  - LOW: General documents, unrecoverable fragments, low-confidence artifacts.
"""

from __future__ import annotations

from typing import Optional


VALID_PRIORITIES = frozenset({"CRITICAL", "HIGH", "MEDIUM", "LOW"})


def determine_priority(
    category: str,
    content_preview: Optional[str] = None,
    status: Optional[str] = None,
    confidence_score: int = 0,
) -> str:
    """Determine forensic priority level based on deterministic rules.

    Args:
        category: Artifact category (from classifier.py).
        content_preview: First ~200 bytes decoded as UTF-8 (optional).
        status: Recovery status string (optional).
        confidence_score: Numeric confidence score 0–100.

    Returns:
        Priority string from VALID_PRIORITIES.
    """
    preview_lower = (content_preview or "").lower()

    # UNRECOVERABLE artifacts with very low confidence are always LOW priority
    if status == "UNRECOVERABLE" and confidence_score < 20:
        return "LOW"

    # Critical indicators in content preview
    critical_indicators = (
        "password",
        "private key",
        "sudo_exec",
        "admin",
        "root",
        "credential",
        "secret",
    )
    if any(indicator in preview_lower for indicator in critical_indicators):
        return "CRITICAL"

    # Category-based rules
    if category == "PHOTO_MEDIA":
        return "HIGH"

    if category == "DATABASE_LOG":
        financial_indicators = ("amount", "transaction", "balance", "payment", "ledger")
        if any(indicator in preview_lower for indicator in financial_indicators):
            return "HIGH"
        return "MEDIUM"

    if category == "SYSTEM_TRACE":
        return "MEDIUM"

    if category == "BINARY_ARCHIVE":
        return "MEDIUM"

    return "LOW"
