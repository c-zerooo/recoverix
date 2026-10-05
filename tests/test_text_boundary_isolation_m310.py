"""tests/test_text_boundary_isolation_m310.py — Test suite for Milestone 3.10.0:
Bounded Blind Candidate Isolation & Structured Precedence.

Verifies:
1. TXT immediately followed by valid PDF (TXT stops before PDF, PDF independently detected).
2. TXT immediately followed by XML (TXT stops before XML, XML independently detected).
3. TXT immediately followed by JSON (TXT stops before line-separated JSON).
4. Structured candidate inside surrounding printable text (TXT before + structured + TXT after).
5. Multi-format composite evidence (TXT + PDF + XML + JSON partitioned without swallowing).
6. Truncated JSON followed by valid JSON (both discovered, search does not skip downstream JSON).
7. Truncated JSON followed by multiple valid JSONs (all discovered and properly bounded).
8. Negative control: ordinary text mentioning %PDF-1.4 or <?xml without valid document syntax is NOT split.
9. Recovery-level accounting: TXT + PDF composite evidence has zero double-accounting (V_txt + V_pdf <= total).
10. Benchmark baseline validation: seed 42 achieves 6/6 passed and 0 forensic violations.
"""

from __future__ import annotations

import pytest

from backend.app.recovery.scanner import scan_evidence
from backend.app.recovery.tracer import execute_traced_recoveries
from tests.test_pdf_recovery import build_minimal_pdf
from benchmark.run_baseline import run_baseline_benchmark


# ── Scenario 1: TXT immediately followed by valid PDF ────────────────────────

def test_01_txt_immediately_followed_by_valid_pdf():
    """1. TXT candidate stops before PDF; PDF is independently detected with zero overlap."""
    txt_data = (
        b"Host: forensic-audit-node-01\n"
        b"Service: systemd-journald\n"
        b"Status: Active and logging recovery events\n"
        b"Severity: Info\n"
    ) * 3
    pdf_data = build_minimal_pdf()
    evidence = txt_data + pdf_data

    candidates = scan_evidence(evidence)
    txt_cands = [c for c in candidates if c.format == "txt"]
    pdf_cands = [c for c in candidates if c.format == "pdf"]

    assert len(txt_cands) >= 1, "Expected at least 1 TXT candidate"
    assert len(pdf_cands) >= 1, "Expected at least 1 PDF candidate"

    txt_cand = txt_cands[0]
    pdf_cand = pdf_cands[0]

    # TXT candidate boundaries
    assert txt_cand.offset == 0
    assert txt_cand.estimated_end_offset == len(txt_data)

    # PDF candidate boundaries
    assert pdf_cand.offset == len(txt_data)
    assert pdf_cand.estimated_end_offset == len(evidence)

    # Strict isolation: TXT must stop exactly at PDF start without swallowing
    assert txt_cand.estimated_end_offset <= pdf_cand.offset
    assert not (txt_cand.offset <= pdf_cand.offset and (txt_cand.estimated_end_offset or 0) >= (pdf_cand.estimated_end_offset or 0))


# ── Scenario 2: TXT immediately followed by XML ──────────────────────────────

def test_02_txt_immediately_followed_by_xml():
    """2. TXT candidate stops before XML; XML is independently detected with zero overlap."""
    txt_data = (
        b"Configuration dump timestamp: 2026-10-06T00:00:00Z\n"
        b"Environment: Production\n"
        b"Cluster: us-central1-recovery\n"
        b"Node: worker-042\n"
    ) * 2
    xml_data = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<catalog><book id="bk101"><title>Forensic Analysis</title></book></catalog>'
    )
    evidence = txt_data + xml_data

    candidates = scan_evidence(evidence)
    txt_cands = [c for c in candidates if c.format == "txt"]
    xml_cands = [c for c in candidates if c.format == "xml"]

    assert len(txt_cands) >= 1, "Expected at least 1 TXT candidate"
    assert len(xml_cands) >= 1, "Expected at least 1 XML candidate"

    txt_cand = txt_cands[0]
    xml_cand = xml_cands[0]

    assert txt_cand.offset == 0
    assert txt_cand.estimated_end_offset == len(txt_data)
    assert xml_cand.offset == len(txt_data)
    assert xml_cand.estimated_end_offset == len(evidence)
    assert txt_cand.estimated_end_offset <= xml_cand.offset


# ── Scenario 3: TXT immediately followed by JSON ─────────────────────────────

def test_03_txt_immediately_followed_by_json():
    """3. TXT candidate stops before line-separated JSON container."""
    txt_data = (
        b"Application system log entry alpha.\n"
        b"Application system log entry beta.\n"
        b"Application system log entry gamma.\n"
    ) * 3
    json_data = b'{"status": "success", "records_processed": 100, "verified": true}'
    evidence = txt_data + json_data

    candidates = scan_evidence(evidence)
    txt_cands = [c for c in candidates if c.format == "txt"]
    json_cands = [c for c in candidates if c.format == "json"]

    assert len(txt_cands) >= 1, "Expected at least 1 TXT candidate"
    assert len(json_cands) >= 1, "Expected at least 1 JSON candidate"

    txt_cand = txt_cands[0]
    json_cand = json_cands[0]

    assert txt_cand.offset == 0
    assert txt_cand.estimated_end_offset == len(txt_data)
    assert json_cand.offset == len(txt_data)
    assert json_cand.estimated_end_offset == len(evidence)
    assert txt_cand.estimated_end_offset <= json_cand.offset


# ── Scenario 4: Structured candidate inside surrounding printable text ───────

def test_04_structured_candidate_surrounded_by_text():
    """4. Structured candidate embedded between two text blocks partitions them into two isolated runs."""
    txt_before = (
        b"Header preamble log records start here.\n"
        b"Processing batches for forensic verification.\n"
        b"Checkpoint 1 completed with zero faults.\n"
    ) * 2
    pdf_mid = build_minimal_pdf()
    txt_after = (
        b"Trailer postamble log records resume here.\n"
        b"Verification resumed following embedded document.\n"
        b"All systems nominal and operational.\n"
    ) * 2

    evidence = txt_before + pdf_mid + txt_after

    candidates = scan_evidence(evidence)
    txt_cands = [c for c in candidates if c.format == "txt"]
    pdf_cands = [c for c in candidates if c.format == "pdf"]

    assert len(txt_cands) == 2, f"Expected exactly 2 TXT candidates (before and after), got {len(txt_cands)}"
    assert len(pdf_cands) == 1, f"Expected exactly 1 PDF candidate, got {len(pdf_cands)}"

    cand_before = txt_cands[0]
    cand_pdf = pdf_cands[0]
    cand_after = txt_cands[1]

    # Contiguous non-overlapping partitioning
    assert cand_before.offset == 0
    assert cand_before.estimated_end_offset == len(txt_before)

    assert cand_pdf.offset == len(txt_before)
    assert cand_pdf.estimated_end_offset == len(txt_before) + len(pdf_mid)

    assert cand_after.offset == len(txt_before) + len(pdf_mid)
    assert cand_after.estimated_end_offset == len(evidence)

    # Neither TXT run swallows the PDF
    assert cand_before.estimated_end_offset <= cand_pdf.offset
    assert cand_pdf.estimated_end_offset <= cand_after.offset


# ── Scenario 5: Multi-format composite evidence ──────────────────────────────

def test_05_multi_format_composite_evidence():
    """5. Multi-format composite evidence (TXT + PDF + XML + JSON) partitions all candidates cleanly."""
    txt_part = (
        b"Section 1: Forensic analysis summary.\n"
        b"Reviewing multi-artifact container disk dump.\n"
        b"Beginning evidence partition inspection.\n"
    ) * 2
    pdf_part = build_minimal_pdf()
    xml_part = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<manifest><case id="CAS-001"><status>OPEN</status></case></manifest>'
    )
    json_part = b'{"module": "recovery", "code": 200, "verified_items": [1, 2, 3]}'

    evidence = txt_part + pdf_part + xml_part + json_part

    candidates = scan_evidence(evidence)

    txt_cands = [c for c in candidates if c.format == "txt"]
    pdf_cands = [c for c in candidates if c.format == "pdf"]
    xml_cands = [c for c in candidates if c.format == "xml"]
    json_cands = [c for c in candidates if c.format == "json"]

    assert len(txt_cands) >= 1, "Expected TXT candidate"
    assert len(pdf_cands) >= 1, "Expected PDF candidate"
    assert len(xml_cands) >= 1, "Expected XML candidate"
    assert len(json_cands) >= 1, "Expected JSON candidate"

    c_txt = txt_cands[0]
    c_pdf = pdf_cands[0]
    c_xml = xml_cands[0]
    c_json = json_cands[0]

    # Verify offset progression
    assert c_txt.offset == 0
    assert c_txt.estimated_end_offset == len(txt_part)

    assert c_pdf.offset == len(txt_part)
    assert c_pdf.estimated_end_offset == len(txt_part) + len(pdf_part)

    assert c_xml.offset == len(txt_part) + len(pdf_part)
    assert c_xml.estimated_end_offset == len(txt_part) + len(pdf_part) + len(xml_part)

    assert c_json.offset == len(txt_part) + len(pdf_part) + len(xml_part)
    assert c_json.estimated_end_offset == len(evidence)

    # Verify non-overlapping boundaries
    assert c_txt.estimated_end_offset <= c_pdf.offset
    assert c_pdf.estimated_end_offset <= c_xml.offset
    assert c_xml.estimated_end_offset <= c_json.offset


# ── Scenario 6: Truncated JSON followed by valid JSON ─────────────────────────

def test_06_truncated_json_followed_by_valid_json():
    """6. Truncated JSON does not jump past subsequent valid JSON candidates."""
    trunc_json = b'{"items": [1, 2, 3'
    gap = b"\n\n"
    valid_json = b'{"response": "ok", "count": 42}'
    evidence = trunc_json + gap + valid_json

    candidates = scan_evidence(evidence)
    json_cands = [c for c in candidates if c.format == "json"]

    assert len(json_cands) == 2, f"Expected both truncated and valid JSON candidates, got {len(json_cands)}"

    c_trunc = json_cands[0]
    c_valid = json_cands[1]

    # Truncated container: estimated_end_offset is None
    assert c_trunc.offset == 0
    assert c_trunc.estimated_end_offset is None

    # Valid container: exact offsets preserved
    expected_valid_offset = len(trunc_json) + len(gap)
    assert c_valid.offset == expected_valid_offset
    assert c_valid.estimated_end_offset == len(evidence)


# ── Scenario 7: Truncated JSON followed by multiple valid JSONs ──────────────

def test_07_truncated_json_followed_by_multiple_valid_jsons():
    """7. Truncated JSON followed by multiple valid JSONs discovers all downstream containers."""
    trunc_json = b'{"header": {"nested": [10, 20'
    v1 = b'{"id": 1, "name": "alpha"}'
    v2 = b'{"id": 2, "name": "beta"}'
    evidence = trunc_json + b"\n" + v1 + b"\n" + v2

    candidates = scan_evidence(evidence)
    json_cands = [c for c in candidates if c.format == "json"]

    assert len(json_cands) == 3, f"Expected 3 JSON candidates, got {len(json_cands)}"

    # First is truncated
    assert json_cands[0].offset == 0
    assert json_cands[0].estimated_end_offset is None

    # Second is closed v1
    exp_offset_v1 = len(trunc_json) + 1
    assert json_cands[1].offset == exp_offset_v1
    assert json_cands[1].estimated_end_offset == exp_offset_v1 + len(v1)

    # Third is closed v2
    exp_offset_v2 = exp_offset_v1 + len(v1) + 1
    assert json_cands[2].offset == exp_offset_v2
    assert json_cands[2].estimated_end_offset == exp_offset_v2 + len(v2)


# ── Scenario 8: Negative control (ordinary text not split) ───────────────────

def test_08_negative_control_text_with_embedded_keywords_not_split():
    """8. Ordinary text mentioning %PDF-1.4 or <?xml without valid syntax is NOT split."""
    text_body = (
        b"Log entry: Document header format %PDF-1.4 was parsed by upstream filter.\n"
        b"Notice: Also saw <?xml version='1.0'?> in description metadata field.\n"
        b"No actual embedded PDF or XML objects follow; this is purely plaintext log.\n"
        b"All lines continue as normal text without structural boundaries.\n"
    ) * 2
    prefix = b"\x00" * 32
    suffix = b"\x00" * 32
    evidence = prefix + text_body + suffix

    candidates = scan_evidence(evidence)
    pdf_cands = [c for c in candidates if c.format == "pdf"]
    xml_cands = [c for c in candidates if c.format == "xml"]
    txt_cands = [c for c in candidates if c.format == "txt"]

    # No spurious valid structured candidates with closed boundaries
    assert len(pdf_cands) == 0, f"Expected 0 PDF candidates, got {len(pdf_cands)}"
    assert all(c.estimated_end_offset is None for c in xml_cands), "Expected no closed XML candidates"

    # Single unbroken text candidate spanning the entire text body without being split
    assert len(txt_cands) == 1, f"Expected exactly 1 contiguous TXT candidate, got {len(txt_cands)}"
    assert txt_cands[0].offset == len(prefix)
    assert txt_cands[0].estimated_end_offset == len(prefix) + len(text_body)


# ── Scenario 9: Recovery-level accounting: TXT + PDF ──────────────────────────

def test_09_recovery_level_accounting_txt_and_pdf():
    """9. Recovery-level accounting verifies V_txt + V_pdf <= total evidence bytes with 0 double-accounting."""
    txt_part = (
        b"System audit log node 01 starting operation.\n"
        b"Performing initial physical drive verification.\n"
        b"All sectors scanned and verified clean.\n"
    ) * 2
    pdf_part = build_minimal_pdf()
    evidence = txt_part + pdf_part

    runs = execute_traced_recoveries("composite.bin", evidence, detection_mode="blind")

    # Find the TXT and PDF recovery runs
    txt_runs = [r for r in runs if r.format == "txt"]
    pdf_runs = [r for r in runs if r.format == "pdf"]

    assert len(txt_runs) >= 1, "Expected at least 1 TXT recovery run"
    assert len(pdf_runs) >= 1, "Expected at least 1 PDF recovery run"

    r_txt = txt_runs[0]
    r_pdf = pdf_runs[0]

    # Exact byte counts
    assert r_txt.total_verified_bytes == len(txt_part)
    assert r_pdf.total_verified_bytes == len(pdf_part)
    assert r_pdf.status == "FULLY_RECOVERED"

    # Non-overlapping accounting: total verified bytes across both runs equals evidence length
    total_verified = r_txt.total_verified_bytes + r_pdf.total_verified_bytes
    assert total_verified <= len(evidence)
    assert total_verified == len(evidence)

    # Neither claims the other's evidence territory
    assert r_txt.total_input_bytes == len(txt_part)
    assert r_pdf.total_input_bytes == len(pdf_part)


# ── Scenario 10: Benchmark baseline validation ───────────────────────────────

def test_10_benchmark_baseline_seed42_validation():
    """10. Benchmark baseline runner achieves 6/6 passed and 0 forensic violations."""
    report = run_baseline_benchmark(seed=42, verbose=False)

    summary = report["summary"]
    assert summary["scenarios_passed"] == 6, f"Expected 6 scenarios passed, got {summary['scenarios_passed']}"
    assert summary["scenarios_total"] == 6, f"Expected 6 total scenarios, got {summary['scenarios_total']}"
    assert summary["total_forensic_violations"] == 0, f"Expected 0 forensic violations, got {summary['total_forensic_violations']}"
    assert summary["overall_passed"] is True, "Expected overall benchmark status to be PASSED"
    assert len(report["forensic_violations"]) == 0, f"Expected empty forensic violation list, got {report['forensic_violations']}"
