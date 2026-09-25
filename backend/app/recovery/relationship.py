"""
relationship.py — Deterministic TXT/CSV fragment relationship identification.

Decides whether two detected fragments can belong to the same artifact, using
deterministic evidence signals only. No ground-truth manifest is consulted and
no missing byte is ever produced here.

Signals evaluated
-----------------
  * ``same_format``       — both fragments were identified as the same format.
  * ``order_valid``       — Fragment A starts strictly before Fragment B and does
                            not overlap it.
  * ``schema_compatible`` — for CSV, the fragments share a modal column count and
                            delimiter; for TXT, both bodies decode as UTF-8.
  * ``bounded_gap``       — the unobserved region between the fragments is a
                            non-empty gap no larger than ``MAX_GAP``.

A pair is *joinable* only when every signal holds. This milestone deliberately
supports exactly ``Fragment A + unknown bounded gap + Fragment B``; no
multi-fragment optimisation and no graph structure is built.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from backend.app.recovery.fragment_detector import DetectedFragment

MIN_GAP = 1
MAX_GAP = 4096


@dataclass(frozen=True)
class FragmentRelationship:
    """Deterministic verdict on whether two fragments belong to one artifact.

    Attributes:
        fragment_a_id: Identifier of the earlier fragment.
        fragment_b_id: Identifier of the later fragment.
        format: Shared detected format.
        same_format: Both fragments resolved to the same format.
        order_valid: A precedes B without overlap.
        schema_compatible: Structural schema agrees across the two fragments.
        bounded_gap: A non-empty gap within [MIN_GAP, MAX_GAP] separates them.
        observed_gap: Size in bytes of the unobserved region between the fragments.
        signals: Full per-signal detail for the audit trail.
    """

    fragment_a_id: str
    fragment_b_id: str
    format: str
    same_format: bool
    order_valid: bool
    schema_compatible: bool
    bounded_gap: bool
    observed_gap: int
    signals: dict[str, Any]

    @property
    def is_joinable(self) -> bool:
        """True when every deterministic signal supports a shared artifact."""
        return (
            self.same_format
            and self.order_valid
            and self.schema_compatible
            and self.bounded_gap
        )

    @property
    def relationship_type(self) -> str:
        return "BOUNDED_GAP" if self.is_joinable else "UNRELATED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "fragment_a_id": self.fragment_a_id,
            "fragment_b_id": self.fragment_b_id,
            "format": self.format,
            "same_format": self.same_format,
            "order_valid": self.order_valid,
            "schema_compatible": self.schema_compatible,
            "bounded_gap": self.bounded_gap,
            "observed_gap": self.observed_gap,
            "is_joinable": self.is_joinable,
            "relationship_type": self.relationship_type,
            "signals": self.signals,
        }


def _schema_compatible(a: DetectedFragment, b: DetectedFragment) -> tuple[bool, dict[str, Any]]:
    """Compare the deterministic structural schema of two fragments."""
    if a.format == "csv":
        same_delim = a.delimiter is not None and a.delimiter == b.delimiter
        modal_a = a.modal_column_count
        modal_b = b.modal_column_count
        same_width = modal_a is not None and modal_a == modal_b
        detail = {
            "delimiter_a": a.delimiter,
            "delimiter_b": b.delimiter,
            "same_delimiter": same_delim,
            "modal_columns_a": modal_a,
            "modal_columns_b": modal_b,
            "same_column_width": same_width,
        }
        return same_delim and same_width, detail

    try:
        a.data.decode("utf-8")
        utf8_a = True
    except UnicodeDecodeError:
        utf8_a = False
    try:
        b.data.decode("utf-8")
        utf8_b = True
    except UnicodeDecodeError:
        utf8_b = False
    detail = {
        "utf8_a": utf8_a,
        "utf8_b": utf8_b,
        "line_count_a": a.line_count,
        "line_count_b": b.line_count,
    }
    return utf8_a and utf8_b, detail


def assess_fragment_pair(
    a: DetectedFragment,
    b: DetectedFragment,
    *,
    min_gap: int = MIN_GAP,
    max_gap: int = MAX_GAP,
) -> FragmentRelationship:
    """Assess whether fragments *a* and *b* can belong to the same artifact.

    Args:
        a: Earlier fragment.
        b: Later fragment.
        min_gap: Smallest acceptable unobserved gap.
        max_gap: Largest acceptable unobserved gap.

    Returns:
        A FragmentRelationship carrying every individual signal.
    """
    if a.format != b.format:
        fmt = "txt"
    else:
        fmt = a.format

    same_format = a.format == b.format
    order_valid = a.offset < b.offset and a.end_offset <= b.offset
    gap = b.offset - a.end_offset if order_valid else 0
    bounded_gap = order_valid and min_gap <= gap <= max_gap
    schema_ok, schema_detail = _schema_compatible(a, b)

    signals: dict[str, Any] = {
        "offset_a": a.offset,
        "end_offset_a": a.end_offset,
        "offset_b": b.offset,
        "bytes_between": gap,
        "gap_range_searched": [min_gap, max_gap],
        "schema": schema_detail,
    }

    return FragmentRelationship(
        fragment_a_id=a.fragment_id,
        fragment_b_id=b.fragment_id,
        format=fmt,
        same_format=same_format,
        order_valid=order_valid,
        schema_compatible=schema_ok,
        bounded_gap=bounded_gap,
        observed_gap=gap,
        signals=signals,
    )


def select_fragment_pairs(
    fragments: list[DetectedFragment],
    *,
    min_gap: int = MIN_GAP,
    max_gap: int = MAX_GAP,
) -> list[tuple[DetectedFragment, DetectedFragment, FragmentRelationship]]:
    """Return every joinable ordered (A, B) pair, deterministically ordered.

    With at most two fragments this yields at most one pair. The scan is
    exhaustive over ordered pairs but bounded by the fragment count, so it stays
    a linear-cost check rather than a combinatorial search.
    """
    pairs: list[tuple[DetectedFragment, DetectedFragment, FragmentRelationship]] = []
    ordered = sorted(fragments, key=lambda f: (f.offset, f.fragment_id))
    for i, a in enumerate(ordered):
        for b in ordered[i + 1 :]:
            rel = assess_fragment_pair(a, b, min_gap=min_gap, max_gap=max_gap)
            if rel.is_joinable:
                pairs.append((a, b, rel))
    return pairs
