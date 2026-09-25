"""
scanner.py — Deterministic candidate-fragment scanner.

Accepts raw evidence bytes and scans for registered format signatures,
producing a list of Candidate objects representing detected artifact
regions.

The scanner:
  - scans left to right, one byte at a time
  - records every signature match it finds
  - never reads outside the byte buffer
  - never mutates the input
  - produces deterministic results for identical input
  - does not crash on malformed or truncated evidence

For TXT/CSV (synthetic boundary markers):
  - detects [SYNTHETIC_ARTIFACT_START]
  - locates the corresponding [SYNTHETIC_ARTIFACT_END]
  - differentiates TXT from CSV by content heuristics
  - records the candidate region including both markers

For PNG:
  - detects the 8-byte PNG magic signature
  - records the candidate start
  - leaves estimated_end_offset as None (no full PNG parser)

This module does NOT perform recovery, carving, reconstruction,
confidence scoring, classification, or AI work.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from backend.app.recovery.signatures import (
    SYNTHETIC_START_MARKER,
    SYNTHETIC_END_MARKER,
    PNG_SIGNATURE,
)


@dataclass(frozen=True)
class Candidate:
    """A detected candidate artifact region in the evidence.

    Attributes:
        candidate_id: Unique sequential identifier (``"cand-0"``, ``"cand-1"``, …).
        format: Detected format (``"txt"``, ``"csv"``, ``"png"``).
        mime_type: MIME type string.
        category: Human-readable category (``"text"``, ``"image"``).
        offset: Byte offset of the detected header in the evidence.
        detected_header_length: Length of the header/signature that was matched.
        estimated_end_offset: Byte offset one past the last byte of the
            candidate region, or ``None`` if the end could not be determined.
        detection_method: Label describing how this candidate was found.
    """

    candidate_id: str
    format: str
    mime_type: str
    category: str
    offset: int
    detected_header_length: int
    estimated_end_offset: Optional[int]
    detection_method: str


# ── Content heuristic for TXT vs CSV ────────────────────────────────

def _classify_synthetic_content(body: bytes) -> str:
    """Classify the content between synthetic markers as TXT or CSV.

    Heuristic:
      - If the first non-empty line after the start marker contains a
        comma, the artifact is classified as CSV.
      - Otherwise, it is classified as TXT.

    This mirrors the generator's convention:
      - ``_make_txt`` writes ``filename: {name}`` as the first body line.
      - ``_make_csv`` writes comma-separated rows directly.
    """
    try:
        text = body.decode("utf-8", errors="replace")
    except Exception:
        return "txt"  # default fallback

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if "," in stripped:
            return "csv"
        return "txt"

    return "txt"


# ── Scanner ─────────────────────────────────────────────────────────

def scan_evidence(data: bytes) -> List[Candidate]:
    """Scan *data* for registered format signatures.

    Scans left to right, recording every match.  Synthetic boundary
    markers produce one candidate per matched START/END pair (or
    START-to-end-of-data if no END is found).  PNG magic bytes produce
    a candidate with ``estimated_end_offset=None``.

    Args:
        data: Raw evidence bytes.  Never mutated.

    Returns:
        An ordered list of Candidate objects, sorted by offset.
        Empty list if *data* is empty or contains no matches.
    """
    if len(data) == 0:
        return []

    candidates: List[Candidate] = []
    evidence_len = len(data)

    # ── Pass 1: scan for synthetic boundary markers ─────────────
    _scan_synthetic(data, evidence_len, candidates)

    # ── Pass 2: scan for PNG magic bytes ────────────────────────
    _scan_png(data, evidence_len, candidates)

    # Sort by offset for deterministic ordering, then by candidate_id
    # for stability when two candidates share an offset.
    candidates.sort(key=lambda c: (c.offset, c.candidate_id))

    # Assign sequential candidate IDs after sorting.
    final: List[Candidate] = []
    for idx, c in enumerate(candidates):
        final.append(Candidate(
            candidate_id=f"cand-{idx}",
            format=c.format,
            mime_type=c.mime_type,
            category=c.category,
            offset=c.offset,
            detected_header_length=c.detected_header_length,
            estimated_end_offset=c.estimated_end_offset,
            detection_method=c.detection_method,
        ))

    return final


def _scan_synthetic(
    data: bytes,
    evidence_len: int,
    candidates: List[Candidate],
) -> None:
    """Find all synthetic boundary-marker pairs in *data*.

    For each [SYNTHETIC_ARTIFACT_START]:
      - search for the next [SYNTHETIC_ARTIFACT_END]
      - if found, the candidate spans from the start marker through the
        end marker (inclusive of marker bytes)
      - if not found, estimated_end_offset is None (truncated marker)
      - content between the markers is used to classify TXT vs CSV
    """
    start_marker = SYNTHETIC_START_MARKER
    end_marker = SYNTHETIC_END_MARKER
    start_len = len(start_marker)
    end_len = len(end_marker)

    search_from = 0

    while search_from <= evidence_len - start_len:
        # Find the next start marker.
        pos = data.find(start_marker, search_from)
        if pos == -1:
            break

        # Look for the corresponding end marker after this start marker.
        body_start = pos + start_len
        end_pos = data.find(end_marker, body_start)

        if end_pos != -1:
            # End marker found — candidate spans [pos, end_pos + end_len).
            estimated_end = end_pos + end_len
            body = data[body_start:end_pos]
        else:
            # Truncated: no end marker found.
            estimated_end = None
            body = data[body_start:]

        # Classify TXT vs CSV based on content.
        fmt = _classify_synthetic_content(body)
        mime_type = "text/plain" if fmt == "txt" else "text/csv"

        candidates.append(Candidate(
            candidate_id="",  # assigned later
            format=fmt,
            mime_type=mime_type,
            category="text",
            offset=pos,
            detected_header_length=start_len,
            estimated_end_offset=estimated_end,
            detection_method="synthetic_boundary",
        ))

        # Advance past this start marker to find more.
        search_from = pos + start_len


def _scan_png(
    data: bytes,
    evidence_len: int,
    candidates: List[Candidate],
) -> None:
    """Find all PNG magic-byte signatures in *data*.

    Each match produces a candidate with estimated_end_offset=None
    because determining the PNG end requires a full chunk parser,
    which is outside the scanner's scope.
    """
    sig = PNG_SIGNATURE
    sig_len = len(sig)

    search_from = 0

    while search_from <= evidence_len - sig_len:
        pos = data.find(sig, search_from)
        if pos == -1:
            break

        candidates.append(Candidate(
            candidate_id="",  # assigned later
            format="png",
            mime_type="image/png",
            category="image",
            offset=pos,
            detected_header_length=sig_len,
            estimated_end_offset=None,
            detection_method="magic_bytes",
        ))

        # Advance past this signature to find more.
        search_from = pos + sig_len
