"""
classifier.py — Deterministic artifact category classification.

Classifies recovered artifacts into forensic categories based on file format,
content preview, and structural metadata. AI never invents or overrides these
deterministic classifications.

Categories:
  - SYSTEM_TRACE: Authentication logs, system event traces, sudo/admin activity.
  - DATABASE_LOG: CSV/database records, transaction logs, tabular data.
  - PHOTO_MEDIA: Image files (PNG, JPG, etc.).
  - BINARY_ARCHIVE: Executables, archives, and opaque binary formats.
  - DOCUMENT: General text documents, notes, and unclassified text.
"""

from __future__ import annotations

from typing import Optional


# Valid category values matching frontend ArtifactCategory type
VALID_CATEGORIES = frozenset({
    "SYSTEM_TRACE",
    "DATABASE_LOG",
    "PHOTO_MEDIA",
    "BINARY_ARCHIVE",
    "DOCUMENT",
})


def classify_artifact(
    fmt: str,
    content_preview: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> str:
    """Classify an artifact into a forensic category based on deterministic rules.

    Args:
        fmt: File format string (e.g. "txt", "csv", "png").
        content_preview: First ~200 bytes decoded as UTF-8 (optional).
        metadata: Artifact metadata dict (optional).

    Returns:
        Category string from VALID_CATEGORIES.
    """
    fmt_lower = fmt.lower() if fmt else ""
    preview_lower = (content_preview or "").lower()

    # Image formats → PHOTO_MEDIA
    if fmt_lower in ("png", "jpg", "jpeg", "gif", "bmp", "tiff", "webp"):
        return "PHOTO_MEDIA"

    # CSV → DATABASE_LOG
    if fmt_lower == "csv":
        return "DATABASE_LOG"

    # Binary/archive formats → BINARY_ARCHIVE
    if fmt_lower in ("exe", "dll", "zip", "tar", "gz", "bin", "elf"):
        return "BINARY_ARCHIVE"

    # Text files: inspect content preview for system trace indicators
    if fmt_lower in ("txt", "log", "text"):
        system_trace_indicators = (
            "auth_success",
            "auth_fail",
            "sudo",
            "sudo_exec",
            "login",
            "ip address",
            "session",
            "sshd",
            "pam_unix",
        )
        if any(indicator in preview_lower for indicator in system_trace_indicators):
            return "SYSTEM_TRACE"
        return "DOCUMENT"

    # Fallback: check content preview for any system trace signals
    system_trace_indicators = (
        "auth_success",
        "auth_fail",
        "sudo",
        "sudo_exec",
        "login",
    )
    if any(indicator in preview_lower for indicator in system_trace_indicators):
        return "SYSTEM_TRACE"

    return "DOCUMENT"
