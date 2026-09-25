"""
fragment_detector.py — Deterministic TXT/CSV fragment detector.

Operates on evidence bytes ONLY. It never reads a ground-truth manifest, never
consults :mod:`backend.app.generator.fragment_generator`, and never assumes that
a byte range is a fragment because a fixture said so.

Detection strategy
------------------
A fragment boundary is only reported where the evidence itself proves one. The
detector scans left to right and splits the evidence into maximal runs of
text-plausible bytes, using a non-text byte run as the only seam evidence:

  * every byte in a run must be printable ASCII, TAB, CR, LF, or a well-formed
    UTF-8 multi-byte sequence;
  * a maximal run of non-text bytes terminates the current fragment;
  * a fragment is a whole number of lines (a leading partial line is dropped and
    a trailing partial line terminates the run, because a physical truncation
    leaves a dangling partial line).

This means a *physically absent* gap that leaves two valid text blocks directly
adjacent is NOT detectable, and this module correctly reports a single fragment
in that case. Fabricating a seam there would be a false positive, so it does not.

For CSV the detector additionally records deterministic structural signals
(delimiter, per-row column counts, header row) which
:mod:`backend.app.recovery.relationship` uses to judge whether two fragments can
belong to the same artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

TEXT_FORMATS = ("txt", "csv")

# Minimum plausible fragment size. Below this, a "fragment" is more likely to be
# incidental noise inside a binary region than a recovered text artifact.
MIN_FRAGMENT_BYTES = 8

_CSV_DELIMITERS = (",", ";", "\t", "|")


@dataclass(frozen=True)
class DetectedFragment:
    """One maximal text-structured run located in the evidence.

    Attributes:
        fragment_id: Stable identifier, ``"frag-0"``, ``"frag-1"``, …
        format: ``"txt"`` or ``"csv"``.
        offset: Byte offset of the first byte of the fragment in the evidence.
        length: Byte length of :attr:`data`.
        data: The fragment bytes, exactly as present in the evidence.
        line_count: Number of complete lines in the fragment.
        ends_with_newline: Whether the fragment terminates on a line boundary.
        is_truncated: True when the fragment does not end on a line boundary,
            i.e. the evidence stops mid-line (physical truncation).
        delimiter: For CSV, the detected field delimiter; ``None`` for TXT.
        column_counts: For CSV, the parsed column count of each row.
        header_line: For CSV, the first row when the fragment is a valid header.
    """

    fragment_id: str
    format: str
    offset: int
    length: int
    data: bytes
    line_count: int
    ends_with_newline: bool
    is_truncated: bool
    delimiter: Optional[str] = None
    column_counts: tuple[int, ...] = ()
    header_line: Optional[bytes] = None

    @property
    def end_offset(self) -> int:
        """Byte offset one past the last byte of this fragment."""
        return self.offset + self.length

    @property
    def modal_column_count(self) -> Optional[int]:
        """Most common CSV column count, ties broken by the smaller count."""
        if not self.column_counts:
            return None
        counts: dict[int, int] = {}
        for c in self.column_counts:
            counts[c] = counts.get(c, 0) + 1
        return min(counts, key=lambda c: (-counts[c], c))


def _text_run_extent(data: bytes, start: int) -> int:
    """Return the end offset of the maximal text-plausible run at *start*."""
    i = start
    n = len(data)
    while i < n:
        b = data[i]
        if b in (9, 10, 13) or 32 <= b <= 126:
            i += 1
            continue
        if b < 0x80:
            return i  # C0 control byte (incl. NUL) terminates the run
        # Multi-byte UTF-8: accept only if a complete, decodable sequence.
        seq_len = 2 if (b & 0xE0) == 0xC0 else 3 if (b & 0xF0) == 0xE0 else 4 if (b & 0xF8) == 0xF0 else 0
        if seq_len == 0 or i + seq_len > n:
            return i
        try:
            data[i : i + seq_len].decode("utf-8")
        except UnicodeDecodeError:
            return i
        i += seq_len
    return n


def _detect_delimiter(lines: Sequence[str]) -> Optional[str]:
    """Pick the delimiter yielding the most consistent column count."""
    best: Optional[str] = None
    best_key: Optional[tuple[int, int]] = None
    for delim in _CSV_DELIMITERS:
        counts = [line.count(delim) for line in lines]
        if not counts or min(counts) == 0:
            continue
        consistent = len(set(counts)) == 1
        key = (1 if consistent else 0, min(counts))
        if best_key is None or key > best_key:
            best, best_key = delim, key
    return best


def _csv_signatures(
    text: str,
) -> tuple[Optional[str], tuple[int, ...], Optional[bytes]]:
    """Derive delimiter, per-row column counts, and header line for CSV text."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return None, (), None
    delim = _detect_delimiter(lines)
    if delim is None:
        return None, (), None
    column_counts = tuple(len(ln.split(delim)) for ln in lines)
    header = lines[0].encode("utf-8") if len(column_counts) >= 2 else None
    return delim, column_counts, header


def detect_text_fragments(
    evidence: bytes,
    fmt: str = "txt",
    min_fragment_bytes: int = MIN_FRAGMENT_BYTES,
) -> list[DetectedFragment]:
    """Detect TXT/CSV fragments in *evidence* using evidence bytes only.

    Args:
        evidence: Raw evidence bytes. Never mutated.
        fmt: ``"txt"`` or ``"csv"``.
        min_fragment_bytes: Discard runs shorter than this many bytes.

    Returns:
        Fragments ordered by ascending offset. Empty when the evidence contains
        no text-plausible run of at least *min_fragment_bytes* bytes.
    """
    normalized = fmt.lower().strip(".")
    if normalized not in TEXT_FORMATS:
        raise ValueError(f"Unsupported fragment format {fmt!r}; expected txt or csv")
    if not evidence:
        return []

    fragments: list[DetectedFragment] = []
    n = len(evidence)
    cursor = 0

    while cursor < n:
        run_start = cursor
        run_end = _text_run_extent(evidence, run_start)

        if run_end == run_start:
            # Non-text byte: this is separator evidence, not a fragment.
            # Advance one byte and re-test so multi-byte separators are skipped
            # safely without ever treating them as content.
            cursor += 1
            continue

        # A non-text byte run is a hard fragment boundary, so the first line after
        # it is a genuine fragment start. Only a *trailing* partial line is trimmed:
        # bytes that stop mid-line are evidence of physical truncation.
        raw = evidence[run_start:run_end]
        nl = raw.find(b"\n")
        if nl == -1:
            # A single-line text file is legitimate and has no terminator. Accept
            # this run only when it reaches the very end of the evidence, which
            # makes it a complete final line rather than an interior slice of a
            # longer line. It is not line-terminated, so it cannot be proven
            # complete and is reported with is_truncated.
            if run_end != len(evidence) or len(raw) < min_fragment_bytes:
                cursor = run_end
                continue
            body = raw
            body_offset = run_start
            ends_with_newline = False
        else:
            body = raw
            body_offset = run_start
            ends_with_newline = body.endswith(b"\n")
            if not ends_with_newline:
                cut = body.rfind(b"\n")
                if cut == -1:
                    cursor = run_end
                    continue
                body = body[: cut + 1]

        if len(body) < min_fragment_bytes:
            cursor = run_end
            continue

        text = body.decode("utf-8", errors="replace")
        delimiter: Optional[str] = None
        column_counts: tuple[int, ...] = ()
        header: Optional[bytes] = None
        if normalized == "csv":
            delimiter, column_counts, header = _csv_signatures(text)

        fragments.append(
            DetectedFragment(
                fragment_id=f"frag-{len(fragments)}",
                format=normalized,
                offset=body_offset,
                length=len(body),
                data=body,
                line_count=len(body.splitlines()),
                ends_with_newline=ends_with_newline,
                is_truncated=not ends_with_newline,
                delimiter=delimiter,
                column_counts=column_counts,
                header_line=header,
            )
        )
        cursor = run_end

    return fragments
