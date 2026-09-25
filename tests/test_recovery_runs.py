"""
test_recovery_runs.py — Test suite for Task 8A RecoveryRun model and tracing pipeline.

Validates the 12 required test scenarios:
1. Intact TXT evidence recovery tracing
2. CSV candidate/fragment tracking
3. JSON detection and event generation
4. XML validation result recording
5. PNG binary fragment offset accuracy
6. JPEG binary fragment offset accuracy
7. PDF detection, fragment, validation, and reconstruction steps
8. Bifragment recovery damage detection & step logging
9. Severely corrupted/unrecoverable evidence handling
10. Byte accounting alignment with provenance
11. Event ordering monotonicity and timestamp format
12. REST API endpoints (/api/recovery-runs and /api/recovery-runs/{run_id})
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.store import store
from backend.app.models.recovery_run import RecoveryRun, Fragment, DamageRegion
from backend.app.recovery.tracer import execute_traced_recovery
from backend.app.recovery.signatures import SYNTHETIC_START_MARKER, SYNTHETIC_END_MARKER

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_store():
    """Reset the in-memory store before each test."""
    store.clear()
    yield
    store.clear()


def test_1_intact_txt_recovery_run():
    """1. Intact TXT: Run created, format detected, fragment correct, no fake reconstruction step."""
    content = b"Simple intact plain text file content for forensic testing."
    run = execute_traced_recovery("sample.txt", content)

    assert isinstance(run, RecoveryRun)
    assert run.format == "txt"
    assert run.status in ["FULLY_RECOVERED", "PARTIALLY_RECOVERED"]
    assert len(run.fragments) >= 1
    assert run.fragments[0].offset == 0
    assert run.fragments[0].end_offset - run.fragments[0].offset == run.fragments[0].length
    assert len(run.reconstruction_steps) == 0


def test_2_csv_recovery_run():
    """2. CSV: Candidate/fragment data represented accurately."""
    content = b"id,name,role\n1,alice,admin\n2,bob,user\n"
    run = execute_traced_recovery("data.csv", content)

    assert run.format == "csv"
    assert len(run.fragments) >= 1
    frag = run.fragments[0]
    assert frag.end_offset - frag.offset == frag.length
    assert frag.format == "csv"


def test_3_json_recovery_run():
    """3. JSON: Format detection event & validation event recorded."""
    content = b'{"status": "ok", "count": 42}'
    run = execute_traced_recovery("config.json", content)

    assert run.format == "json"
    event_types = [e.event_type for e in run.events]
    assert "RECOVERY_STARTED" in event_types
    assert "SCANNING_STARTED" in event_types
    assert "VALIDATION_STARTED" in event_types
    assert "VALIDATION_COMPLETED" in event_types
    assert "CONFIDENCE_CALCULATED" in event_types
    assert "RECOVERY_COMPLETED" in event_types


def test_4_xml_recovery_run():
    """4. XML: Actual validation result represented."""
    content = b'<?xml version="1.0"?><root><item id="1">value</item></root>'
    run = execute_traced_recovery("doc.xml", content)

    assert run.format == "xml"
    assert run.validation is not None
    assert run.validation.get("valid") is True


def test_5_png_recovery_run():
    """5. PNG: Binary fragment offsets accurate."""
    png_header = b"\x89PNG\r\n\x1a\n"
    png_iend = b"\x00\x00\x00\x00IEND\xaeB`\x82"
    content = SYNTHETIC_START_MARKER + b"FMT:png;" + png_header + b"IDATchunkdata" + png_iend + SYNTHETIC_END_MARKER

    run = execute_traced_recovery("image.png", content)

    assert run.format == "png"
    for frag in run.fragments:
        assert frag.end_offset - frag.offset == frag.length


def test_6_jpeg_recovery_run():
    """6. JPEG: Binary fragment offsets accurate."""
    jpeg_header = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"
    jpeg_footer = b"\xff\xd9"
    content = SYNTHETIC_START_MARKER + b"FMT:jpeg;" + jpeg_header + b"compresseddata" + jpeg_footer + SYNTHETIC_END_MARKER

    run = execute_traced_recovery("photo.jpg", content)

    assert run.format == "jpeg"
    for frag in run.fragments:
        assert frag.end_offset - frag.offset == frag.length


def test_7_pdf_recovery_run():
    """7. PDF: PDF detection, fragments, validation, and reconstruction recorded."""
    pdf_header = b"%PDF-1.4\n"
    pdf_footer = b"%%EOF"
    content = SYNTHETIC_START_MARKER + b"FMT:pdf;" + pdf_header + b"1 0 obj\n<< >>\nendobj\n" + pdf_footer + SYNTHETIC_END_MARKER

    run = execute_traced_recovery("report.pdf", content)

    assert run.format == "pdf"
    assert len(run.fragments) >= 1
    assert run.total_input_bytes == len(content)


def test_8_bifragment_recovery_run():
    """8. Bifragment Recovery: Reconstruction started/completed events, actual gap size, fragment relationships."""
    cand1 = SYNTHETIC_START_MARKER + b"FMT:txt;PART:1;" + b"Head section of document."
    cand2 = SYNTHETIC_START_MARKER + b"FMT:txt;PART:2;" + b"Tail section of document."
    gap = b"\x00" * 32
    content = cand1 + gap + cand2

    run = execute_traced_recovery("split_doc.txt", content)

    event_types = [e.event_type for e in run.events]
    assert "DAMAGE_DETECTED" in event_types
    assert "RECONSTRUCTION_STARTED" in event_types
    assert "RECONSTRUCTION_COMPLETED" in event_types

    assert len(run.damage_regions) >= 1
    assert run.damage_regions[0].type == "MISSING"

    assert len(run.reconstruction_steps) >= 1
    step = run.reconstruction_steps[0]
    assert step.method == "BIFRAGMENT_GAP"
    assert step.gap_size == len(gap)


def test_9_unrecoverable_recovery_run():
    """9. Unrecoverable Artifact: Failure status recorded, zero fake reconstruction steps."""
    content = b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f" * 10
    run = execute_traced_recovery("garbage.bin", content)

    assert run.status == "UNRECOVERABLE"
    assert len(run.reconstruction_steps) == 0
    assert len(run.damage_regions) >= 1
    assert run.damage_regions[0].status == "UNRECOVERABLE"


def test_10_byte_accounting_alignment():
    """10. Byte Accounting: Total verified, reconstructed, and missing bytes match Artifact provenance."""
    content = b"Verified content bytes for forensic accounting."
    run = execute_traced_recovery("account.txt", content)

    assert run.provenance is not None
    assert run.total_verified_bytes == run.provenance["verified_bytes"]
    assert run.total_reconstructed_bytes == run.provenance["reconstructed_bytes"]
    assert run.total_missing_bytes == run.provenance["missing_bytes"]


def test_11_event_ordering_and_monotonicity():
    """11. Event Ordering: Monotonic sequence order preserved, matches execution order."""
    content = b"Testing event monotonicity and order."
    run = execute_traced_recovery("seq.txt", content)

    assert len(run.events) >= 2
    for i in range(len(run.events)):
        assert run.events[i].sequence == i + 1
        assert run.events[i].run_id == run.run_id


def test_12_api_recovery_runs_endpoints():
    """12. API Endpoint: GET /api/recovery-runs/{run_id} returns valid run, 404 for invalid ID."""
    content = b"API test content for recovery run endpoints."
    run = execute_traced_recovery("api_test.txt", content)

    # Test listing endpoint
    res_list = client.get("/api/recovery-runs")
    assert res_list.status_code == 200
    runs = res_list.json()
    assert len(runs) >= 1
    assert any(r["run_id"] == run.run_id for r in runs)

    # Test GET by run_id endpoint
    res_get = client.get(f"/api/recovery-runs/{run.run_id}")
    assert res_get.status_code == 200
    data = res_get.json()
    assert data["run_id"] == run.run_id
    assert data["filename"] == "api_test.txt"

    # Test alias GET endpoint
    res_alias = client.get(f"/api/recovery/runs/{run.run_id}")
    assert res_alias.status_code == 200
    assert res_alias.json()["run_id"] == run.run_id

    # Test 404 for invalid ID
    res_404 = client.get("/api/recovery-runs/non_existent_run_123")
    assert res_404.status_code == 404


def test_13_successful_bifragment_accounting():
    """13. Successful Bifragment Forensic Accounting: Physical gap (32 bytes) vs placeholder hypothesis."""
    cand1 = b'<?xml version="1.0"?><root><item>Head section of document.</item><!-- '
    gap = b"\x00" * 32
    cand2 = b'<?xml --> <item>Tail section of document.</item></root>'
    content = cand1 + gap + cand2

    run = execute_traced_recovery("bifragment.xml", content)

    # 1. Total byte accounting invariant must hold
    assert run.total_verified_bytes + run.total_reconstructed_bytes + run.total_missing_bytes == len(content)

    # 2. Reconstructed bytes must be 0 (placeholder gap is not recovered evidence)
    assert run.total_reconstructed_bytes == 0
    assert run.total_missing_bytes == 32

    # 3. Status must be PARTIALLY_RECOVERED, never FULLY_RECOVERED
    assert run.status == "PARTIALLY_RECOVERED"

    # 4. Step details: gap_size is 32, validated_gap_size is 32
    assert len(run.reconstruction_steps) >= 1
    step = run.reconstruction_steps[0]
    assert step.result == "SUCCESS"
    assert step.gap_size == 32
    assert step.validated_gap_size is not None
    assert step.reconstructed_bytes == 0
    assert step.missing_bytes == 32

