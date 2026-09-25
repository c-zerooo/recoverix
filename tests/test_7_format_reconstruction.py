"""
test_7_format_reconstruction.py — Test suite for 7-Format Evidence Reconstruction Pipeline.

Verifies end-to-end 7-format recovery pipeline across all 7 supported formats:
1. TXT: Intact & fragmented text evidence recovery to recovered artifact
2. CSV: Structured candidate carving & validation to recovered artifact
3. JSON: Key-value data signature detection & validation to recovered artifact
4. XML: Document tree signature detection & validation to recovered artifact
5. PNG: Binary image header/IEND carving & validation to recovered artifact
6. JPEG: SOI/EOI binary marker carving & validation to recovered artifact
7. PDF: Document structure & deterministic xref table reconstruction to recovered artifact
"""

from __future__ import annotations

import struct
import zlib
import pytest

from backend.app.recovery.tracer import execute_traced_recovery
from backend.app.models.recovery_run import RecoveryRun
from backend.app.recovery.validators import validate_artifact
from backend.app.recovery.signatures import SYNTHETIC_START_MARKER, SYNTHETIC_END_MARKER


def _make_png_bytes(width: int = 16, height: int = 16) -> bytes:
    png_magic = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF
    ihdr_chunk = struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)

    dummy_data = zlib.compress(b"\x00" * (width * height * 3))
    idat_crc = zlib.crc32(b"IDAT" + dummy_data) & 0xFFFFFFFF
    idat_chunk = struct.pack(">I", len(dummy_data)) + b"IDAT" + dummy_data + struct.pack(">I", idat_crc)

    iend_crc = zlib.crc32(b"IEND") & 0xFFFFFFFF
    iend_chunk = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)

    return png_magic + ihdr_chunk + idat_chunk + iend_chunk


def _make_jpeg_bytes(width: int = 16, height: int = 16) -> bytes:
    soi = b"\xff\xd8"
    eoi = b"\xff\xd9"

    sof0_payload = struct.pack(">BHHB", 8, height, width, 3) + b"\x01\x11\x00\x02\x11\x01\x03\x11\x01"
    sof0_len = len(sof0_payload) + 2
    sof0 = b"\xff\xc0" + struct.pack(">H", sof0_len) + sof0_payload

    sos_payload = b"\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00"
    sos_len = len(sos_payload) + 2
    sos = b"\xff\xda" + struct.pack(">H", sos_len) + sos_payload

    scan_data = b"\x00\x7f"

    return soi + sof0 + sos + scan_data + eoi


def test_format_1_txt_reconstruction():
    """1. TXT: Real damaged evidence to recovered artifact."""
    txt_content = b"User: Alice\nRole: Forensic Investigator\nAction: Log trace verification\n"
    evidence = SYNTHETIC_START_MARKER + b"FMT:txt;" + txt_content + SYNTHETIC_END_MARKER
    padded_evidence = b"\x00" * 16 + evidence + b"\x00" * 16

    run = execute_traced_recovery("audit.txt", padded_evidence)

    assert isinstance(run, RecoveryRun)
    assert run.format == "txt"
    assert run.status in ["FULLY_RECOVERED", "PARTIALLY_RECOVERED"]
    assert run.total_verified_bytes > 0
    assert run.output is not None
    assert "recovered_bytes" in run.output
    recovered_bytes = bytes.fromhex(run.output["recovered_bytes"])
    assert txt_content in recovered_bytes or evidence in recovered_bytes
    val = validate_artifact("txt", recovered_bytes)
    assert val.valid is True


def test_format_2_csv_reconstruction():
    """2. CSV: Real damaged evidence to recovered artifact."""
    csv_content = b"id,timestamp,user,event\n1,2026-09-26T00:00:00Z,admin,login\n2,2026-09-26T00:01:00Z,guest,logout\n"
    evidence = SYNTHETIC_START_MARKER + b"FMT:csv;" + csv_content + SYNTHETIC_END_MARKER
    padded_evidence = b"\xff" * 32 + evidence + b"\xff" * 32

    run = execute_traced_recovery("events.csv", padded_evidence)

    assert run.format == "csv"
    assert run.status in ["FULLY_RECOVERED", "PARTIALLY_RECOVERED"]
    assert run.total_verified_bytes > 0
    assert run.output is not None
    recovered_bytes = bytes.fromhex(run.output["recovered_bytes"])
    assert b"admin,login" in recovered_bytes
    val = validate_artifact("csv", recovered_bytes)
    assert val.valid is True


def test_format_3_json_reconstruction():
    """3. JSON: Real damaged evidence to recovered artifact."""
    json_content = b'{"case_id": "case_101", "status": "active", "evidence_count": 5}'
    evidence = SYNTHETIC_START_MARKER + json_content + SYNTHETIC_END_MARKER
    padded_evidence = b"NOISE_BYTES_BEFORE" + evidence + b"NOISE_BYTES_AFTER"

    run = execute_traced_recovery("metadata.json", padded_evidence)

    assert run.format == "json"
    assert run.status in ["FULLY_RECOVERED", "PARTIALLY_RECOVERED"]
    assert run.total_verified_bytes > 0
    assert run.output is not None
    recovered_bytes = bytes.fromhex(run.output["recovered_bytes"])
    assert b"case_101" in recovered_bytes
    val = validate_artifact("json", recovered_bytes)
    assert val.valid is True


def test_format_4_xml_reconstruction():
    """4. XML: Real damaged evidence to recovered artifact."""
    xml_content = b'<?xml version="1.0" encoding="UTF-8"?><forensic_report><case id="42"><analyst>Agent</analyst></case></forensic_report>'
    evidence = SYNTHETIC_START_MARKER + xml_content + SYNTHETIC_END_MARKER
    padded_evidence = b"\x00\x00" + evidence + b"\x00\x00"

    run = execute_traced_recovery("report.xml", padded_evidence)

    assert run.format == "xml"
    assert run.status in ["FULLY_RECOVERED", "PARTIALLY_RECOVERED"]
    assert run.total_verified_bytes > 0
    assert run.output is not None
    recovered_bytes = bytes.fromhex(run.output["recovered_bytes"])
    assert b"forensic_report" in recovered_bytes
    val = validate_artifact("xml", recovered_bytes)
    assert val.valid is True


def test_format_5_png_reconstruction():
    """5. PNG: Real binary evidence to recovered artifact."""
    raw_png = _make_png_bytes(width=16, height=16)
    padded_evidence = b"\x00" * 32 + raw_png + b"\x00" * 32

    run = execute_traced_recovery("photo.png", padded_evidence)

    assert run.format == "png"
    assert run.status in ["FULLY_RECOVERED", "PARTIALLY_RECOVERED"]
    assert run.total_verified_bytes > 0
    assert run.output is not None
    recovered_bytes = bytes.fromhex(run.output["recovered_bytes"])
    val = validate_artifact("png", recovered_bytes)
    assert val.valid is True


def test_format_6_jpeg_reconstruction():
    """6. JPEG: Real binary evidence to recovered artifact."""
    raw_jpeg = _make_jpeg_bytes(width=16, height=16)
    padded_evidence = b"\xff" * 32 + raw_jpeg + b"\xff" * 32

    run = execute_traced_recovery("evidence.jpg", padded_evidence)

    assert run.format == "jpeg"
    assert run.status in ["FULLY_RECOVERED", "PARTIALLY_RECOVERED"]
    assert run.total_verified_bytes > 0
    assert run.output is not None
    recovered_bytes = bytes.fromhex(run.output["recovered_bytes"])
    val = validate_artifact("jpeg", recovered_bytes)
    assert val.valid is True


def test_format_7_pdf_reconstruction():
    """7. PDF: Real document & damaged xref table reconstruction to recovered artifact."""
    body = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kinds [] /Count 1 /Kids [3 0 R] >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R >>\nendobj\n"
    )
    xref_offset = len(body)
    pdf_bytes = (
        body +
        b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n0000000118 00000 n \n"
        b"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n" +
        f"{xref_offset}\n".encode("ascii") +
        b"%%EOF\n"
    )
    evidence = SYNTHETIC_START_MARKER + b"FMT:pdf;" + pdf_bytes + SYNTHETIC_END_MARKER

    run = execute_traced_recovery("document.pdf", evidence)

    assert run.format == "pdf"
    assert run.status in ["FULLY_RECOVERED", "PARTIALLY_RECOVERED"]
    assert run.total_verified_bytes > 0
    assert run.output is not None
    recovered_bytes = bytes.fromhex(run.output["recovered_bytes"])
    assert b"%PDF-1.4" in recovered_bytes
    assert b"%%EOF" in recovered_bytes
    val = validate_artifact("pdf", recovered_bytes)
    assert val.valid is True
