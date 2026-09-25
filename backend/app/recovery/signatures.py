"""
signatures.py — Controlled format-signature registry.

Defines the signature patterns the scanner uses to identify candidate
artifact regions in raw evidence bytes.  Supports ONLY the formats
required by the current prototype:

  - TXT  (synthetic boundary markers)
  - CSV  (synthetic boundary markers)
  - PNG  (standard PNG magic bytes)

TXT and CSV both use the same [SYNTHETIC_ARTIFACT_START] /
[SYNTHETIC_ARTIFACT_END] markers from the test-harness generator.
They are distinguished by content heuristics after detection.

This module does NOT perform recovery, carving, reconstruction,
classification, or AI work.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


# ── Synthetic boundary markers (shared by TXT and CSV) ──────────────
# These match the markers used in backend/generate_case.py.

SYNTHETIC_START_MARKER: bytes = b"[SYNTHETIC_ARTIFACT_START]"
SYNTHETIC_END_MARKER: bytes = b"[SYNTHETIC_ARTIFACT_END]"

# ── PNG magic bytes ─────────────────────────────────────────────────
# Standard 8-byte PNG file signature (RFC 2083).

PNG_SIGNATURE: bytes = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class FormatSignature:
    """Describes how the scanner identifies one artifact format.

    Attributes:
        format: Short format identifier (e.g. ``"txt"``, ``"csv"``, ``"png"``).
        mime_type: MIME type string.
        category: Human-readable category (e.g. ``"text"``, ``"image"``).
        header: Byte pattern that marks the start of the artifact.
        footer: Optional byte pattern that marks the end.  ``None`` means
                the end cannot be determined from a trailer alone.
        detection_method: Label describing how this signature is detected.
    """

    format: str
    mime_type: str
    category: str
    header: bytes
    footer: Optional[bytes]
    detection_method: str


# ── Registry ────────────────────────────────────────────────────────
# Explicit list — kept small on purpose.  The scanner iterates this.

SIGNATURES: List[FormatSignature] = [
    FormatSignature(
        format="txt",
        mime_type="text/plain",
        category="text",
        header=SYNTHETIC_START_MARKER,
        footer=SYNTHETIC_END_MARKER,
        detection_method="synthetic_boundary",
    ),
    FormatSignature(
        format="csv",
        mime_type="text/csv",
        category="text",
        header=SYNTHETIC_START_MARKER,
        footer=SYNTHETIC_END_MARKER,
        detection_method="synthetic_boundary",
    ),
    FormatSignature(
        format="png",
        mime_type="image/png",
        category="image",
        header=PNG_SIGNATURE,
        footer=None,
        detection_method="magic_bytes",
    ),
]
