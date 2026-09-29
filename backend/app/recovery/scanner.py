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
from typing import List, Optional, Tuple

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

    # ── Pass 6: scan for blind JSON container documents ─────────
    _scan_json(data, evidence_len, candidates)

    # ── Pass 7: scan for blind TXT and CSV candidates ───────────
    _scan_text_and_csv(data, evidence_len, candidates)

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


# Valid JPEG first marker bytes immediately following \xFF\xD8\xFF
VALID_JPEG_FIRST_MARKERS = frozenset({
    0xE0, 0xE1, 0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7,
    0xE8, 0xE9, 0xEA, 0xEB, 0xEC, 0xED, 0xEE, 0xEF,
    0xC0, 0xC1, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7,
    0xC9, 0xCA, 0xCB, 0xCC, 0xCD, 0xCE, 0xCF,
    0xDB, 0xDC, 0xDD, 0xDE, 0xDF, 0xFE,
})


def _scan_jpeg(
    data: bytes,
    evidence_len: int,
    candidates: List[Candidate],
) -> None:
    """Find all JPEG SOI signatures in *data*, requiring a valid following marker."""
    sig = JPEG_SOI
    sig_len = len(sig)

    search_from = 0

    while search_from <= evidence_len - sig_len:
        pos = data.find(sig, search_from)
        if pos == -1:
            break

        # A valid JPEG SOI must be immediately followed by 0xFF and a valid marker byte
        if pos + 3 < evidence_len and data[pos + 2] == 0xFF and data[pos + 3] in VALID_JPEG_FIRST_MARKERS:
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
                    detected_header_length=sig_len + 2,
                    estimated_end_offset=estimated_end,
                    detection_method="magic_bytes",
                )
            )

        search_from = pos + 1



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


def _find_xml_closing_boundary(
    data: bytes,
    header_pos: int,
    max_window: int = 4 * 1024 * 1024,
) -> Optional[int]:
    """Find the exact closing boundary of the XML root element starting at *header_pos*.

    Handles:
      - XML declaration (<?xml ... ?>)
      - doctype declarations (<!DOCTYPE ... >)
      - comments (<!-- ... -->)
      - processing instructions (<? ... ?>)
      - self-closing root tag (<root ... />)
      - CDATA sections with fake closing tags (<![CDATA[ </root> ]]>)
      - comments with fake closing tags (<!-- </root> -->)
      - attribute quotes containing '>' or fake closing tags

    Returns:
        Byte offset one past the last byte of the root element (e.g. after '</root>'),
        or None if truncated or not found within max_window.
    """
    n = min(len(data), header_pos + max_window)
    next_xml = data.find(XML_HEADER_SIGNATURE, header_pos + len(XML_HEADER_SIGNATURE))
    if next_xml != -1 and next_xml < n:
        n = next_xml

    decl_end = data.find(b"?>", header_pos)
    if decl_end == -1 or decl_end > header_pos + 1024 or decl_end >= n:
        return None
    i = decl_end + 2

    root_tag = None
    while i < n:
        while i < n and data[i] in b" \t\r\n":
            i += 1
        if i >= n:
            break
        if data.startswith(b"<!--", i):
            c_end = data.find(b"-->", i + 4)
            if c_end == -1:
                return None
            i = c_end + 3
            continue
        if data.startswith(b"<?", i):
            pi_end = data.find(b"?>", i + 2)
            if pi_end == -1:
                return None
            i = pi_end + 2
            continue
        if data.startswith(b"<!DOCTYPE", i) or data.startswith(b"<!doctype", i):
            j = i + 9
            has_bracket = False
            while j < n:
                if data[j : j + 1] == b"[":
                    has_bracket = True
                elif data[j : j + 1] == b"]":
                    has_bracket = False
                elif data[j : j + 1] == b">" and not has_bracket:
                    i = j + 1
                    break
                j += 1
            else:
                return None
            continue
        if data[i : i + 1] == b"<":
            tag_start = i + 1
            if tag_start < n and (data[tag_start : tag_start + 1].isalpha() or data[tag_start : tag_start + 1] in b"_:"):
                j = tag_start
                while j < n and (data[j : j + 1].isalnum() or data[j : j + 1] in b"_.:-"):
                    j += 1
                root_tag = data[tag_start:j]
                i = j
                break
            else:
                return None
        else:
            i += 1

    if not root_tag:
        return None

    in_quote = None
    while i < n:
        b = data[i : i + 1]
        if in_quote:
            if b == in_quote:
                in_quote = None
            i += 1
            continue
        if b in (b'"', b"'"):
            in_quote = b
            i += 1
            continue
        if b == b"/":
            if i + 1 < n and data[i + 1 : i + 2] == b">":
                return i + 2
        if b == b">":
            i += 1
            break
        i += 1
    else:
        return None

    in_quote = None
    in_tag = False
    closing_target = b"</" + root_tag
    opening_target = b"<" + root_tag
    root_depth = 1

    while i < n:
        if not in_tag:
            if data.startswith(b"<!--", i):
                c_end = data.find(b"-->", i + 4)
                if c_end == -1:
                    return None
                i = c_end + 3
                continue
            if data.startswith(b"<![CDATA[", i):
                cd_end = data.find(b"]]>", i + 9)
                if cd_end == -1:
                    return None
                i = cd_end + 3
                continue
            if data.startswith(closing_target, i):
                j = i + len(closing_target)
                while j < n and data[j : j + 1] in b" \t\r\n":
                    j += 1
                if j < n and data[j : j + 1] == b">":
                    root_depth -= 1
                    if root_depth == 0:
                        return j + 1
                    i = j + 1
                    continue
            if data.startswith(opening_target, i):
                next_b = data[i + len(opening_target) : i + len(opening_target) + 1]
                if next_b in b" \t\r\n/>":
                    k = i + len(opening_target)
                    tag_quote = None
                    is_self_closing = False
                    while k < n:
                        tb = data[k : k + 1]
                        if tag_quote:
                            if tb == tag_quote:
                                tag_quote = None
                            k += 1
                            continue
                        if tb in (b'"', b"'"):
                            tag_quote = tb
                            k += 1
                            continue
                        if tb == b"/":
                            if k + 1 < n and data[k + 1 : k + 2] == b">":
                                is_self_closing = True
                                k += 2
                                break
                        if tb == b">":
                            k += 1
                            break
                        k += 1
                    else:
                        return None

                    if not is_self_closing:
                        root_depth += 1
                    i = k
                    continue
            if data[i : i + 1] == b"<":
                in_tag = True
                i += 1
                continue
            i += 1
        else:
            b = data[i : i + 1]
            if in_quote:
                if b == in_quote:
                    in_quote = None
                i += 1
                continue
            if b in (b'"', b"'"):
                in_quote = b
                i += 1
                continue
            if b == b">":
                in_tag = False
                i += 1
                continue
            i += 1

    return None


def _scan_xml(
    data: bytes,
    evidence_len: int,
    candidates: List[Candidate],
) -> None:
    """Find direct XML header signatures in *data* with bounded end estimation."""
    sig = XML_HEADER_SIGNATURE
    sig_len = len(sig)

    search_from = 0

    while search_from <= evidence_len - sig_len:
        pos = data.find(sig, search_from)
        if pos == -1:
            break

        estimated_end = _find_xml_closing_boundary(data, pos)

        candidates.append(
            Candidate(
                candidate_id="",
                format="xml",
                mime_type="application/xml",
                category="structured",
                offset=pos,
                detected_header_length=sig_len,
                estimated_end_offset=estimated_end,
                detection_method="magic_bytes",
            )
        )
        search_from = pos + sig_len


_JSON_WS = " \t\n\r"
_JSON_LITERALS = ("true", "false", "null")


def _skip_ws(text: str, i: int) -> int:
    while i < len(text) and text[i] in _JSON_WS:
        i += 1
    return i


def _scan_string(text: str, i: int) -> Tuple[int, str]:
    """Scan a JSON string starting at the opening quote.

    Returns (index_after_string, status) where status is "ok" or "unterminated".
    """
    n = len(text)
    j = i + 1
    while j < n:
        c = text[j]
        if c == "\\":
            if j + 1 >= n:
                return n, "unterminated"
            j += 2
            continue
        if c == '"':
            return j + 1, "ok"
        j += 1
    return n, "unterminated"


def _scan_number(text: str, i: int) -> Tuple[int, str]:
    """Scan a JSON number literal.

    Returns (index_after_number, status) where status is "ok" or "invalid".
    """
    n = len(text)
    j = i
    if j < n and text[j] == "-":
        j += 1
    digits_start = j
    while j < n and text[j].isdigit():
        j += 1
    if j == digits_start:
        return j, "invalid"
    if j < n and text[j] == ".":
        j += 1
        frac_start = j
        while j < n and text[j].isdigit():
            j += 1
        if j == frac_start:
            return j, "invalid"
    if j < n and text[j] in "eE":
        j += 1
        if j < n and text[j] in "+-":
            j += 1
        exp_start = j
        while j < n and text[j].isdigit():
            j += 1
        if j == exp_start:
            return j, "invalid"
    if j < n and text[j] not in _JSON_WS and text[j] not in ",}]":
        return j, "invalid"
    return j, "ok"


def _scan_literal(text: str, i: int) -> Tuple[int, str]:
    """Scan true/false/null.

    Returns (index_after_literal, status) where status is "ok", "incomplete", or "invalid".
    """
    n = len(text)
    for lit in _JSON_LITERALS:
        if text.startswith(lit, i):
            end = i + len(lit)
            if end < n and (text[end].isalnum() or text[end] == "_"):
                return end, "invalid"
            return end, "ok"
        if lit.startswith(text[i:n]):
            return n, "incomplete"
    return i, "invalid"


def _find_json_container_extent(
    text: str,
    max_depth: int = 128,
) -> Tuple[Optional[int], bool, bool]:
    """Scan *text* starting at index 0 for a JSON object or array container.

    Returns:
        (end_char_index, is_complete, is_plausible_truncated)
        - If complete: (end_index, True, False)
        - If truncated but structurally plausible: (None, False, True)
        - If invalid/noise: (None, False, False)
    """
    i = _skip_ws(text, 0)
    if i >= len(text) or text[i] not in ("{", "["):
        return None, False, False
    opener = text[i]
    stack = [opener]
    i += 1
    state = "key" if opener == "{" else "value"
    has_content = False

    while i < len(text) and len(stack) <= max_depth:
        if state == "value":
            i = _skip_ws(text, i)
            if i >= len(text):
                return None, False, has_content
            c = text[i]
            if c == "{":
                stack.append("{")
                i += 1
                state = "key"
                has_content = True
                continue
            if c == "[":
                stack.append("[")
                i += 1
                state = "value"
                has_content = True
                continue
            if c == "]" and stack[-1] == "[":
                i += 1
                stack.pop()
                if not stack:
                    return i, True, False
                state = "sep"
                continue
            if c == '"':
                i, st = _scan_string(text, i)
                if st != "ok":
                    return None, False, has_content
                has_content = True
                state = "sep"
                continue
            if c in "tfn":
                i, st = _scan_literal(text, i)
                if st == "incomplete":
                    return None, False, has_content
                if st != "ok":
                    return None, False, False
                has_content = True
                state = "sep"
                continue
            if c == "-" or c.isdigit():
                i, st = _scan_number(text, i)
                if st == "incomplete":
                    return None, False, has_content
                if st != "ok":
                    return None, False, False
                has_content = True
                state = "sep"
                continue
            return None, False, False

        if state == "key":
            i = _skip_ws(text, i)
            if i >= len(text):
                return None, False, has_content
            if text[i] == "}" and stack[-1] == "{":
                i += 1
                stack.pop()
                if not stack:
                    return i, True, False
                state = "sep"
                continue
            if text[i] != '"':
                return None, False, False
            i, st = _scan_string(text, i)
            if st != "ok":
                return None, False, has_content
            has_content = True
            state = "colon"
            continue

        if state == "colon":
            i = _skip_ws(text, i)
            if i >= len(text):
                return None, False, has_content
            if text[i] != ":":
                return None, False, False
            i += 1
            state = "value"
            continue

        if state == "sep":
            if not stack:
                return i, True, False
            i = _skip_ws(text, i)
            if i >= len(text):
                return None, False, has_content
            c = text[i]
            closer = "}" if stack[-1] == "{" else "]"
            if c == ",":
                i += 1
                state = "key" if stack[-1] == "{" else "value"
                continue
            if c == closer:
                i += 1
                stack.pop()
                if not stack:
                    return i, True, False
                state = "sep"
                continue
            return None, False, False

    return None, False, has_content


def _scan_json(
    data: bytes,
    evidence_len: int,
    candidates: List[Candidate],
) -> None:
    """Find all blind JSON container documents (objects and arrays) in *data*."""
    MAX_JSON_WINDOW = 2 * 1024 * 1024  # 2 MiB bounded search window
    MAX_NESTING_DEPTH = 128
    search_from = 0

    while search_from < evidence_len:
        pos_brace = data.find(b"{", search_from)
        pos_bracket = data.find(b"[", search_from)

        if pos_brace == -1 and pos_bracket == -1:
            break
        if pos_brace != -1 and pos_bracket != -1:
            pos = min(pos_brace, pos_bracket)
        else:
            pos = pos_brace if pos_brace != -1 else pos_bracket

        # Avoid redundant duplicate detection if pos is inside an already detected synthetic candidate
        in_synthetic = False
        for c in candidates:
            if c.detection_method == "synthetic_boundary":
                c_end = c.estimated_end_offset if c.estimated_end_offset is not None else evidence_len
                if c.offset <= pos < c_end:
                    in_synthetic = True
                    search_from = c_end
                    break
        if in_synthetic:
            continue

        opener = data[pos : pos + 1]

        # Fast lookahead: inspect first non-whitespace byte
        k = pos + 1
        while k < evidence_len and data[k] in b" \t\r\n":
            k += 1

        if k >= evidence_len:
            search_from = pos + 1
            continue

        next_b = data[k : k + 1]
        if opener == b"{":
            if next_b not in (b'"', b"}"):
                search_from = pos + 1
                continue
        elif opener == b"[":
            if not (next_b in (b'"', b"{", b"[", b"]", b"-", b"t", b"f", b"n") or (b"0" <= next_b <= b"9")):
                search_from = pos + 1
                continue

        window_len = min(evidence_len - pos, MAX_JSON_WINDOW)
        slice_bytes = data[pos : pos + window_len]
        text = slice_bytes.decode("utf-8", errors="replace")

        end_char_index, is_complete, is_plausible_truncated = _find_json_container_extent(
            text, max_depth=MAX_NESTING_DEPTH
        )

        if is_complete and end_char_index is not None:
            doc_bytes = text[:end_char_index].encode("utf-8")
            byte_len = len(doc_bytes)
            estimated_end = pos + byte_len

            # Verify UTF-8 fidelity and validate JSON structure
            try:
                candidate_raw = data[pos:estimated_end]
                candidate_raw.decode("utf-8")
            except UnicodeDecodeError:
                search_from = pos + 1
                continue

            from backend.app.recovery.validators.json import validate_json

            val_res = validate_json(candidate_raw)
            if val_res.valid:
                candidates.append(
                    Candidate(
                        candidate_id="",
                        format="json",
                        mime_type="application/json",
                        category="structured",
                        offset=pos,
                        detected_header_length=1,
                        estimated_end_offset=estimated_end,
                        detection_method="syntax_boundary",
                    )
                )
                search_from = estimated_end
                continue
            else:
                search_from = pos + 1
                continue

        elif not is_complete and is_plausible_truncated:
            from backend.app.recovery.reconstructors.json import (
                _classify_prefix,
                _CLOSABLE,
                _INCOMPLETE,
            )

            cls_res, stack, _ = _classify_prefix(text)
            if cls_res in (_CLOSABLE, _INCOMPLETE) and len(stack) > 0:
                candidates.append(
                    Candidate(
                        candidate_id="",
                        format="json",
                        mime_type="application/json",
                        category="structured",
                        offset=pos,
                        detected_header_length=1,
                        estimated_end_offset=None,
                        detection_method="syntax_boundary",
                    )
                )
                search_from = pos + len(slice_bytes)
                continue
            else:
                search_from = pos + 1
                continue
        else:
            search_from = pos + 1
            continue


def _scan_text_and_csv(
    data: bytes,
    evidence_len: int,
    candidates: List[Candidate],
) -> None:
    """Find blind TXT and CSV candidate runs in *data* based on text-run heuristics and mandatory validation."""
    from backend.app.recovery.validators.csv import validate_csv
    from backend.app.recovery.validators.text import validate_txt

    MIN_CANDIDATE_LEN = 64
    MIN_PRINTABLE_DENSITY = 0.90
    MIN_LOGICAL_NEWLINES = 2

    # Collect ranges occupied by synthetic boundary candidates to preserve synthetic harness behavior
    synthetic_ranges = []
    for c in candidates:
        if c.detection_method == "synthetic_boundary":
            c_end = c.estimated_end_offset if c.estimated_end_offset is not None else evidence_len
            synthetic_ranges.append((c.offset, c_end))

    i = 0
    while i < evidence_len:
        # 1. Skip if current position is inside a synthetic candidate range
        in_synthetic = False
        for s_start, s_end in synthetic_ranges:
            if s_start <= i < s_end:
                i = s_end
                in_synthetic = True
                break
        if in_synthetic:
            continue

        # 2. Skip non-text bytes to locate start of potential text run
        b = data[i]
        is_text_start = False
        step = 1

        if (0x20 <= b <= 0x7E) or b in (9, 10, 13):
            is_text_start = True
        elif 0xC2 <= b <= 0xF4:
            for s in (2, 3, 4):
                if i + s <= evidence_len:
                    try:
                        ch = data[i : i + s].decode("utf-8")
                        if ch.isprintable():
                            is_text_start = True
                            step = s
                            break
                    except UnicodeDecodeError:
                        pass

        if not is_text_start:
            i += 1
            continue

        # Found start of text run
        start = i
        j = i + step
        printable_bytes = step

        # 3. Advance j until a run terminator is encountered
        terminated_on_invalid_utf8 = False
        while j < evidence_len:
            # Check synthetic boundary collision
            collided_synthetic = False
            for s_start, s_end in synthetic_ranges:
                if s_start <= j < s_end:
                    collided_synthetic = True
                    break
            if collided_synthetic:
                break

            jb = data[j]
            # NUL byte is a hard terminator
            if jb == 0:
                break

            # Printable ASCII / whitespace
            if (0x20 <= jb <= 0x7E) or jb in (9, 10, 13):
                printable_bytes += 1
                j += 1
                continue

            # Multi-byte UTF-8
            if 0xC2 <= jb <= 0xF4:
                matched_multibyte = False
                for s in (2, 3, 4):
                    if j + s <= evidence_len:
                        try:
                            ch = data[j : j + s].decode("utf-8")
                            if ch.isprintable():
                                printable_bytes += s
                                j += s
                                matched_multibyte = True
                                break
                        except UnicodeDecodeError:
                            pass
                if matched_multibyte:
                    continue

            # 1-byte control character (not 9, 10, 13)
            if jb < 32 or jb == 127:
                curr_len = (j - start) + 1
                if (printable_bytes / curr_len) < MIN_PRINTABLE_DENSITY:
                    break
                # If two consecutive control bytes, terminate run
                if j + 1 < evidence_len and (data[j + 1] < 32 or data[j + 1] == 127) and data[j + 1] not in (9, 10, 13):
                    break
                j += 1
                continue

            # Any invalid UTF-8 byte terminates the run
            terminated_on_invalid_utf8 = True
            break

        # 4. Trim incomplete trailing UTF-8 sequences and trailing non-printable control bytes
        while j > start:
            try:
                data[start:j].decode("utf-8")
                break
            except UnicodeDecodeError:
                j -= 1

        while j > start and data[j - 1] < 32 and data[j - 1] not in (9, 10, 13):
            j -= 1

        # Trim trailing incomplete lines where appropriate
        if b"\n" in data[start:j]:
            last_nl = data[start:j].rfind(b"\n")
            trailing_segment = data[start + last_nl + 1 : j]
            if trailing_segment:
                has_non_printable = any(
                    (tb < 32 and tb not in (9, 10, 13)) or tb == 127
                    for tb in trailing_segment
                )
                if has_non_printable or terminated_on_invalid_utf8:
                    j = start + last_nl + 1

        run_bytes = data[start:j]
        run_len = len(run_bytes)

        # 5. Check heuristics
        if run_len >= MIN_CANDIDATE_LEN:
            # Standalone whole-buffer text files (no surrounding evidence boundaries)
            # are preserved for the canonical direct fallback recovery path.
            if start == 0 and j == evidence_len:
                i = max(j, i + 1)
                continue

            newlines = run_bytes.count(b"\n") + (run_bytes.count(b"\r") - run_bytes.count(b"\r\n"))
            density = printable_bytes / run_len if run_len > 0 else 0.0

            if newlines >= MIN_LOGICAL_NEWLINES and density >= MIN_PRINTABLE_DENSITY:
                first_nl = run_bytes.find(b"\n")
                first_line_len = (first_nl + 1) if first_nl != -1 else 1

                # 6. Mandatory Validation Gate
                # First test CSV
                val_csv = validate_csv(run_bytes)
                if val_csv.valid:
                    candidates.append(
                        Candidate(
                            candidate_id="",
                            format="csv",
                            mime_type="text/csv",
                            category="text",
                            offset=start,
                            detected_header_length=first_line_len,
                            estimated_end_offset=j,
                            detection_method="heuristic_text_run",
                        )
                    )

                # Then independently test TXT
                val_txt = validate_txt(run_bytes)
                if val_txt.valid:
                    candidates.append(
                        Candidate(
                            candidate_id="",
                            format="txt",
                            mime_type="text/plain",
                            category="text",
                            offset=start,
                            detected_header_length=first_line_len,
                            estimated_end_offset=j,
                            detection_method="heuristic_text_run",
                        )
                    )

        i = max(j, i + 1)
