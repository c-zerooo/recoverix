"""
scanner.py — Deterministic candidate-fragment scanner.

Accepts raw evidence bytes and scans for registered format signatures,
producing a list of Candidate objects representing detected artifact
regions across all 7 supported formats (TXT, CSV, JSON, XML, PNG, JPEG, PDF).

The scanner:
  - scans left to right, one byte at a time
  - records every signature match it finds
  - never reads outside the byte buffer
  - never mutates the input
  - produces deterministic results for identical input
  - does not crash on malformed or truncated evidence

For TXT/CSV/JSON/XML (synthetic boundary markers):
  - detects [SYNTHETIC_ARTIFACT_START]
  - locates the corresponding [SYNTHETIC_ARTIFACT_END]
  - differentiates TXT vs CSV vs JSON vs XML by content heuristics
  - records the candidate region including both markers

For PNG:
  - detects the 8-byte PNG magic signature (\x89PNG\r\n\x1a\n)
  - records the candidate start

For JPEG:
  - detects the 2-byte JPEG SOI signature (\xFF\xD8)
  - searches for EOI marker (\xFF\xD9) to calculate estimated end offset

For PDF:
  - detects the PDF header signature (%PDF-)
  - searches for trailer marker (%%EOF) to calculate estimated end offset

For direct XML:
  - detects '<?xml' header signature

This module does NOT perform recovery, carving, reconstruction,
confidence scoring, classification, or AI work.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List, Optional

from backend.app.recovery.signatures import (
    SYNTHETIC_START_MARKER,
    SYNTHETIC_END_MARKER,
    PNG_SIGNATURE,
    JPEG_SOI,
    JPEG_EOI,
    PDF_HEADER_SIGNATURE,
    PDF_TRAILER_SIGNATURE,
    XML_HEADER_SIGNATURE,
)


@dataclass(frozen=True)
class Candidate:
    """A detected candidate artifact region in the evidence.

    Attributes:
        candidate_id: Unique sequential identifier (``"cand-0"``, ``"cand-1"``, …).
        format: Detected format (``"txt"``, ``"csv"``, ``"json"``, ``"xml"``, ``"png"``, ``"jpeg"``, ``"pdf"``).
        mime_type: MIME type string.
        category: Human-readable category (``"text"``, ``"structured"``, ``"image"``, ``"document"``).
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


# ── Content heuristic for Synthetic Marker Payloads ──────────────────

def _classify_synthetic_content(body: bytes) -> tuple[str, str, str]:
    """Classify the content between synthetic markers as TXT, CSV, JSON, XML, PNG, JPEG, or PDF.

    Returns:
        Tuple of (format, mime_type, category).
    """
    # First check explicit FMT:<format>; header prefix in synthetic marker bodies
    if body.startswith(b"FMT:"):
        end_fmt = body.find(b";")
        if end_fmt != -1:
            tag = body[4:end_fmt].decode("utf-8", errors="ignore").lower()
            if tag == "png":
                return ("png", "image/png", "image")
            elif tag in ("jpeg", "jpg"):
                return ("jpeg", "image/jpeg", "image")
            elif tag == "pdf":
                return ("pdf", "application/pdf", "document")
            elif tag == "txt":
                return ("txt", "text/plain", "text")
            elif tag == "csv":
                return ("csv", "text/csv", "text")
            elif tag == "json":
                return ("json", "application/json", "structured")
            elif tag == "xml":
                return ("xml", "application/xml", "structured")

    # Check magic byte signatures embedded in synthetic body
    if PNG_SIGNATURE in body:
        return ("png", "image/png", "image")
    if JPEG_SOI in body:
        return ("jpeg", "image/jpeg", "image")
    if PDF_HEADER_SIGNATURE in body:
        return ("pdf", "application/pdf", "document")

    try:
        text = body.decode("utf-8", errors="replace").strip()
    except Exception:
        return ("txt", "text/plain", "text")

    if not text:
        return ("txt", "text/plain", "text")

    # Check JSON
    if text.startswith(("{", "[")):
        try:
            json.loads(text)
            return ("json", "application/json", "structured")
        except Exception:
            pass

    # Check XML
    if text.startswith(("<?xml", "<")):
        try:
            ET.fromstring(text)
            return ("xml", "application/xml", "structured")
        except Exception:
            if text.startswith("<?xml"):
                return ("xml", "application/xml", "structured")

    # Check CSV
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if "," in stripped:
            return ("csv", "text/csv", "text")
        break

    return ("txt", "text/plain", "text")


# ── Scanner ─────────────────────────────────────────────────────────

def scan_evidence(data: bytes) -> List[Candidate]:
    """Scan *data* for registered format signatures across 7 formats.

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

    # ── Pass 3: scan for JPEG SOI bytes ─────────────────────────
    _scan_jpeg(data, evidence_len, candidates)

    # ── Pass 4: scan for PDF header bytes ────────────────────────
    _scan_pdf(data, evidence_len, candidates)

    # ── Pass 5: scan for direct XML headers ─────────────────────
    _scan_xml(data, evidence_len, candidates)

    # Deduplicate candidates sharing exact same offset and format
    seen = set()
    unique_candidates = []
    for c in candidates:
        key = (c.offset, c.format)
        if key not in seen:
            seen.add(key)
            unique_candidates.append(c)

    # Sort by offset for deterministic ordering, then by format
    unique_candidates.sort(key=lambda c: (c.offset, c.format))

    # Assign sequential candidate IDs after sorting.
    final: List[Candidate] = []
    for idx, c in enumerate(unique_candidates):
        final.append(
            Candidate(
                candidate_id=f"cand-{idx}",
                format=c.format,
                mime_type=c.mime_type,
                category=c.category,
                offset=c.offset,
                detected_header_length=c.detected_header_length,
                estimated_end_offset=c.estimated_end_offset,
                detection_method=c.detection_method,
            )
        )

    return final


def _scan_synthetic(
    data: bytes,
    evidence_len: int,
    candidates: List[Candidate],
) -> None:
    """Find all synthetic boundary-marker pairs in *data*."""
    start_marker = SYNTHETIC_START_MARKER
    end_marker = SYNTHETIC_END_MARKER
    start_len = len(start_marker)
    end_len = len(end_marker)

    search_from = 0

    while search_from <= evidence_len - start_len:
        pos = data.find(start_marker, search_from)
        if pos == -1:
            break

        body_start = pos + start_len
        end_pos = data.find(end_marker, body_start)

        if end_pos != -1:
            estimated_end = end_pos + end_len
            body = data[body_start:end_pos]
        else:
            estimated_end = None
            body = data[body_start:]

        fmt, mime_type, category = _classify_synthetic_content(body)

        candidates.append(
            Candidate(
                candidate_id="",
                format=fmt,
                mime_type=mime_type,
                category=category,
                offset=pos,
                detected_header_length=start_len,
                estimated_end_offset=estimated_end,
                detection_method="synthetic_boundary",
            )
        )

        search_from = pos + start_len


def _scan_png(
    data: bytes,
    evidence_len: int,
    candidates: List[Candidate],
) -> None:
    """Find all PNG magic-byte signatures in *data*."""
    sig = PNG_SIGNATURE
    sig_len = len(sig)

    search_from = 0

    while search_from <= evidence_len - sig_len:
        pos = data.find(sig, search_from)
        if pos == -1:
            break

        iend_pos = data.find(b"IEND", pos + sig_len)
        estimated_end = (iend_pos + 8) if iend_pos != -1 else None

        candidates.append(
            Candidate(
                candidate_id="",
                format="png",
                mime_type="image/png",
                category="image",
                offset=pos,
                detected_header_length=sig_len,
                estimated_end_offset=estimated_end,
                detection_method="magic_bytes",
            )
        )

        search_from = pos + sig_len


def _scan_jpeg(
    data: bytes,
    evidence_len: int,
    candidates: List[Candidate],
) -> None:
    """Find all JPEG SOI signatures in *data*."""
    sig = JPEG_SOI
    sig_len = len(sig)

    search_from = 0

    while search_from <= evidence_len - sig_len:
        pos = data.find(sig, search_from)
        if pos == -1:
            break

        # Check for EOI marker after SOI to estimate end
        eoi_pos = data.find(JPEG_EOI, pos + sig_len)
        estimated_end = (eoi_pos + len(JPEG_EOI)) if eoi_pos != -1 else None

        candidates.append(
            Candidate(
                candidate_id="",
                format="jpeg",
                mime_type="image/jpeg",
                category="image",
                offset=pos,
                detected_header_length=sig_len,
                estimated_end_offset=estimated_end,
                detection_method="magic_bytes",
            )
        )

        search_from = pos + sig_len


def _scan_pdf(
    data: bytes,
    evidence_len: int,
    candidates: List[Candidate],
) -> None:
    """Find all PDF header signatures in *data*."""
    sig = PDF_HEADER_SIGNATURE
    sig_len = len(sig)

    search_from = 0

    while search_from <= evidence_len - sig_len:
        pos = data.find(sig, search_from)
        if pos == -1:
            break

        # Check for %%EOF marker after header to estimate end
        eof_pos = data.rfind(PDF_TRAILER_SIGNATURE, pos + sig_len)
        if eof_pos != -1:
            estimated_end = eof_pos + len(PDF_TRAILER_SIGNATURE)
            if estimated_end + 1 <= evidence_len and data[estimated_end:estimated_end + 2] in (b"\r\n", b"\n\r"):
                estimated_end += 2
            elif estimated_end < evidence_len and data[estimated_end:estimated_end + 1] in (b"\n", b"\r"):
                estimated_end += 1
        else:
            estimated_end = None

        candidates.append(
            Candidate(
                candidate_id="",
                format="pdf",
                mime_type="application/pdf",
                category="document",
                offset=pos,
                detected_header_length=sig_len,
                estimated_end_offset=estimated_end,
                detection_method="magic_bytes",
            )
        )

        search_from = pos + sig_len


def _scan_xml(
    data: bytes,
    evidence_len: int,
    candidates: List[Candidate],
) -> None:
    """Find direct XML header signatures in *data*."""
    sig = XML_HEADER_SIGNATURE
    sig_len = len(sig)

    search_from = 0

    while search_from <= evidence_len - sig_len:
        pos = data.find(sig, search_from)
        if pos == -1:
            break

        candidates.append(
            Candidate(
                candidate_id="",
                format="xml",
                mime_type="application/xml",
                category="structured",
                offset=pos,
                detected_header_length=sig_len,
                estimated_end_offset=None,
                detection_method="magic_bytes",
            )
        )

        search_from = pos + sig_len
