"""tests/test_pdf_multi_candidate_m39.py — Focused tests for Milestone 3.9.0:
Bounded PDF Candidate Scope & Multi-PDF Isolation.

Verifies:
1. Two valid PDFs separated by zero padding are strictly isolated with no swallowing.
2. Two adjacent valid PDFs have zero overlap and boundary continuity.
3. Truncated first PDF does not steal the second PDF's trailer.
4. Internal "%PDF-" and "%%EOF" markers inside active streams do not create ghost candidates.
5. Incremental PDF with multiple %%EOF markers preserves the final revision boundary.
6. Multi-candidate isolation prevents over-carving and double-accounting.
"""

from __future__ import annotations

import pytest

from backend.app.recovery.scanner import scan_evidence
from tests.test_pdf_recovery import build_minimal_pdf


def build_pdf_with_stream_markers() -> bytes:
    """Construct a valid PDF containing %PDF- and %%EOF markers inside an active stream."""
    stream_content = b"Content containing %PDF-1.4 and %PDF-1.7 and %%EOF marker inside stream"
    stream_len = len(stream_content)
    body = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Count 1 /Kids [3 0 R] >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Length " + str(stream_len).encode("ascii") + b" >>\nstream\n"
        + stream_content + b"\nendstream\nendobj\n"
    )
    xref_offset = len(body)
    trailer = (
        b"xref\n"
        b"0 5\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000052 00000 n \n"
        b"0000000108 00000 n \n"
        b"0000000155 00000 n \n"
        b"trailer\n"
        b"<< /Size 5 /Root 1 0 R >>\n"
        b"startxref\n"
        + f"{xref_offset}\n".encode("ascii")
        + b"%%EOF\n"
    )
    return body + trailer


def build_incremental_pdf() -> bytes:
    """Construct a valid PDF containing two revisions and two %%EOF markers."""
    body_rev1 = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Count 1 /Kids [3 0 R] >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R >>\nendobj\n"
    )
    xref1_offset = len(body_rev1)
    rev1 = body_rev1 + (
        b"xref\n"
        b"0 4\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000052 00000 n \n"
        b"0000000108 00000 n \n"
        b"trailer\n"
        b"<< /Size 4 /Root 1 0 R >>\n"
        b"startxref\n"
        + f"{xref1_offset}\n".encode("ascii")
        + b"%%EOF\n"
    )

    body_rev2 = b"4 0 obj\n<< /Type /Annot /Subtype /Text >>\nendobj\n"
    xref2_offset = len(rev1) + len(body_rev2)
    rev2 = body_rev2 + (
        b"xref\n"
        b"4 1\n"
        + f"{len(rev1):010d} 00000 n \n".encode("ascii")
        + b"trailer\n"
        b"<< /Size 5 /Root 1 0 R /Prev "
        + f"{xref1_offset} >>\n".encode("ascii")
        + b"startxref\n"
        + f"{xref2_offset}\n".encode("ascii")
        + b"%%EOF\n"
    )
    return rev1 + rev2


def test_01_two_pdfs_with_zero_padding():
    """TEST 1: Two valid PDFs separated by zero padding are isolated without swallowing."""
    pdf1 = build_minimal_pdf()
    pdf2 = build_minimal_pdf()
    gap_padding = b"\x00" * 2048
    evidence = pdf1 + gap_padding + pdf2

    candidates = [c for c in scan_evidence(evidence) if c.format == "pdf"]

    assert len(candidates) == 2, f"Expected exactly 2 PDF candidates, got {len(candidates)}"

    cand1, cand2 = candidates[0], candidates[1]

    # First candidate boundaries
    assert cand1.offset == 0
    assert cand1.estimated_end_offset == len(pdf1)

    # Second candidate boundaries
    expected_start2 = len(pdf1) + len(gap_padding)
    expected_end2 = len(evidence)
    assert cand2.offset == expected_start2
    assert cand2.estimated_end_offset == expected_end2

    # Verify no overlap and candidate 1 does NOT contain candidate 2
    assert cand1.estimated_end_offset <= cand2.offset
    assert not (cand1.offset <= cand2.offset and cand1.estimated_end_offset >= cand2.estimated_end_offset)


def test_02_adjacent_pdfs():
    """TEST 2: Two adjacent valid PDFs have zero overlap and exact adjacency."""
    pdf1 = build_minimal_pdf()
    pdf2 = build_minimal_pdf()
    evidence = pdf1 + pdf2

    candidates = [c for c in scan_evidence(evidence) if c.format == "pdf"]

    assert len(candidates) == 2, f"Expected exactly 2 PDF candidates, got {len(candidates)}"

    cand1, cand2 = candidates[0], candidates[1]

    assert cand1.offset == 0
    assert cand1.estimated_end_offset == len(pdf1)

    assert cand2.offset == len(pdf1)
    assert cand2.estimated_end_offset == len(evidence)

    # Candidate 1 ends exactly where Candidate 2 begins
    assert cand1.estimated_end_offset == cand2.offset
    assert not (cand1.offset <= cand2.offset and cand1.estimated_end_offset > cand2.offset)


def test_03_truncated_pdf_followed_by_valid_pdf():
    """TEST 3: Truncated first PDF does not steal second PDF's trailer."""
    pdf1_truncated = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    pdf2 = build_minimal_pdf()
    gap_padding = b"\x00" * 1024
    evidence = pdf1_truncated + gap_padding + pdf2

    candidates = [c for c in scan_evidence(evidence) if c.format == "pdf"]

    assert len(candidates) == 2, f"Expected exactly 2 PDF candidates, got {len(candidates)}"

    cand1, cand2 = candidates[0], candidates[1]

    # Truncated PDF must have estimated_end_offset=None (no trailer in territory)
    assert cand1.offset == 0
    assert cand1.estimated_end_offset is None

    # Valid PDF2 must retain its genuine start and end
    expected_start2 = len(pdf1_truncated) + len(gap_padding)
    expected_end2 = len(evidence)
    assert cand2.offset == expected_start2
    assert cand2.estimated_end_offset == expected_end2


def test_04_internal_pdf_marker_inside_stream():
    """TEST 4: %PDF- and %%EOF inside an active stream do not create ghost candidates."""
    pdf_with_stream = build_pdf_with_stream_markers()
    candidates = [c for c in scan_evidence(pdf_with_stream) if c.format == "pdf"]

    assert len(candidates) == 1, f"Expected exactly 1 PDF candidate, got {len(candidates)}"

    cand = candidates[0]
    assert cand.offset == 0
    assert cand.estimated_end_offset == len(pdf_with_stream)


def test_05_incremental_pdf_multiple_eof():
    """TEST 5: PDF with incremental updates preserves the final revision %%EOF."""
    incremental_pdf = build_incremental_pdf()
    candidates = [c for c in scan_evidence(incremental_pdf) if c.format == "pdf"]

    assert len(candidates) == 1, f"Expected exactly 1 PDF candidate, got {len(candidates)}"

    cand = candidates[0]
    assert cand.offset == 0
    # Must capture full document ending at final %%EOF, not the first revision %%EOF
    assert cand.estimated_end_offset == len(incremental_pdf)


def make_pdf_with_extra_body(extra_obj: bytes) -> bytes:
    """Helper to construct a valid PDF containing extra object/comment/string content."""
    body = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Count 1 /Kids [3 0 R] >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R >>\nendobj\n"
        + extra_obj
    )
    xref_offset = len(body)
    trailer = (
        b"xref\n"
        b"0 5\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000052 00000 n \n"
        b"0000000108 00000 n \n"
        b"0000000155 00000 n \n"
        b"trailer\n"
        b"<< /Size 5 /Root 1 0 R >>\n"
        b"startxref\n"
        + f"{xref_offset}\n".encode("ascii")
        + b"%%EOF\n"
    )
    return body + trailer


def test_06_literal_string_false_header_outside_stream():
    """TEST 6: %PDF-1.4 inside a literal string outside a stream does not spawn a ghost candidate."""
    pdf_bytes = make_pdf_with_extra_body(b"4 0 obj\n<< /Title (Doc conforms to %PDF-1.4 spec) >>\nendobj\n")
    candidates = [c for c in scan_evidence(pdf_bytes) if c.format == "pdf"]

    assert len(candidates) == 1, f"Expected exactly 1 PDF candidate, got {len(candidates)}"
    assert candidates[0].offset == 0
    assert candidates[0].estimated_end_offset == len(pdf_bytes)


def test_07_comment_false_header_outside_stream():
    """TEST 7: %PDF-1.7 inside a comment outside a stream does not spawn a ghost candidate."""
    pdf_bytes = make_pdf_with_extra_body(b"% Note: Updated according to %PDF-1.7 rules\n4 0 obj\n<< /Type /Metadata >>\nendobj\n")
    candidates = [c for c in scan_evidence(pdf_bytes) if c.format == "pdf"]

    assert len(candidates) == 1, f"Expected exactly 1 PDF candidate, got {len(candidates)}"
    assert candidates[0].offset == 0
    assert candidates[0].estimated_end_offset == len(pdf_bytes)


def test_08_object_syntax_false_header_outside_stream():
    """TEST 8: %PDF-1.5 inside object syntax outside a stream does not spawn a ghost candidate."""
    pdf_bytes = make_pdf_with_extra_body(b"4 0 obj\n<< /Note (See %PDF-1.5 manual) >>\nendobj\n")
    candidates = [c for c in scan_evidence(pdf_bytes) if c.format == "pdf"]

    assert len(candidates) == 1, f"Expected exactly 1 PDF candidate, got {len(candidates)}"
    assert candidates[0].offset == 0
    assert candidates[0].estimated_end_offset == len(pdf_bytes)
