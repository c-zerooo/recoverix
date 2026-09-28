"""
test_pipeline_a_migration.py — Milestone 2 Phase 2.3 Migration Regression Suite.

Verifies that POST /api/cases/{case_id}/analyze delegates to the canonical traced
recovery engine, enforces Milestone 1 invariants, preserves multi-candidate discovery,
establishes Approach C storage linkage without duplicate RecoveryRuns, and maintains
full API contract backward compatibility.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.store import store
from backend.app.recovery.signatures import (
    SYNTHETIC_START_MARKER,
    SYNTHETIC_END_MARKER,
)
from backend.app.generator import generate_fragment_case, STANDARD_FIXTURES, EvidenceDisk
from tests.test_pdf_recovery import build_minimal_pdf

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_store():
    """Ensure clean store before and after every test."""
    store.clear()
    yield
    store.clear()


# ── Scenario A: Intact TXT ──────────────────────────────────────────

def test_pipeline_a_intact_txt():
    """Scenario A: Intact TXT evidence produces FULLY_RECOVERED, V=len, R=0, M=0."""
    case = store.create_case("Case Intact TXT")
    payload = SYNTHETIC_START_MARKER + b"FORMAT=txt\nHeader: Incident\nBody: All systems normal.\n" + SYNTHETIC_END_MARKER
    store.add_evidence(case.case_id, "doc.txt", payload)

    res = client.post(f"/api/cases/{case.case_id}/analyze")
    assert res.status_code == 200
    data = res.json()
    assert data["case_id"] == case.case_id
    assert data["status"] == "COMPLETED"
    assert data["artifact_count"] == 1
    assert len(data["artifacts"]) == 1

    art = data["artifacts"][0]
    assert art["format"] == "txt"
    assert art["status"] == "FULLY_RECOVERED"
    assert art["confidence_score"] == 100
    assert art["provenance"]["verified_bytes"] == len(payload)
    assert art["provenance"]["reconstructed_bytes"] == 0
    assert art["provenance"]["missing_bytes"] == 0
    assert art["provenance"]["validation_status"] == "PASSED"


# ── Scenario B: Intact CSV ──────────────────────────────────────────

def test_pipeline_a_intact_csv():
    """Scenario B: Intact CSV evidence produces FULLY_RECOVERED, V=len, R=0, M=0."""
    case = store.create_case("Case Intact CSV")
    _, payload = STANDARD_FIXTURES["csv"]
    store.add_evidence(case.case_id, "ledger.csv", payload)

    res = client.post(f"/api/cases/{case.case_id}/analyze")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "COMPLETED"
    assert data["artifact_count"] == 1

    art = data["artifacts"][0]
    assert art["format"] == "csv"
    assert art["status"] == "FULLY_RECOVERED"
    assert art["confidence_score"] == 100
    assert art["provenance"]["verified_bytes"] == len(payload)
    assert art["provenance"]["reconstructed_bytes"] == 0
    assert art["provenance"]["missing_bytes"] == 0
    assert art["provenance"]["validation_status"] == "PASSED"


# ── Scenario C: Seed-42 Fragmented TXT ──────────────────────────────

def test_pipeline_a_seed_42_fragmented_txt():
    """Scenario C: Seed-42 fragmented TXT must yield PARTIALLY_RECOVERED with V=83, R=0, M=209."""
    case = store.create_case("Case Fragmented TXT")
    _, orig_bytes_txt = STANDARD_FIXTURES["txt"]
    fc_txt = generate_fragment_case(orig_bytes_txt, fmt="txt", seed=42, scenario="fragmented")
    m_txt = fc_txt.to_manifest()
    disk_txt = EvidenceDisk(len(orig_bytes_txt), fill=0x00)
    for frag in m_txt["fragments"]:
        disk_txt.write(frag["offset"], orig_bytes_txt[frag["offset"]:frag["end_offset"]])

    store.add_evidence(case.case_id, "server.txt", disk_txt.data)

    res = client.post(f"/api/cases/{case.case_id}/analyze")
    assert res.status_code == 200
    data = res.json()
    assert data["artifact_count"] == 1

    art = data["artifacts"][0]
    assert art["format"] == "txt"
    assert art["status"] == "PARTIALLY_RECOVERED"
    assert art["status"] != "FULLY_RECOVERED"
    assert art["provenance"]["verified_bytes"] == 83
    assert art["provenance"]["reconstructed_bytes"] == 0
    assert art["provenance"]["missing_bytes"] == 209
    assert art["provenance"]["validation_status"] == "PASSED"


# ── Scenario D: Seed-42 Fragmented CSV ──────────────────────────────

def test_pipeline_a_seed_42_fragmented_csv():
    """Scenario D: Seed-42 fragmented CSV must yield PARTIALLY_RECOVERED with V=289, R=0, M=57."""
    case = store.create_case("Case Fragmented CSV")
    _, orig_bytes_csv = STANDARD_FIXTURES["csv"]
    fc_csv = generate_fragment_case(orig_bytes_csv, fmt="csv", seed=42, scenario="fragmented")
    m_csv = fc_csv.to_manifest()
    disk_csv = EvidenceDisk(len(orig_bytes_csv), fill=0x00)
    for frag in m_csv["fragments"]:
        disk_csv.write(frag["offset"], orig_bytes_csv[frag["offset"]:frag["end_offset"]])

    store.add_evidence(case.case_id, "data.csv", disk_csv.data)

    res = client.post(f"/api/cases/{case.case_id}/analyze")
    assert res.status_code == 200
    data = res.json()
    assert data["artifact_count"] == 1

    art = data["artifacts"][0]
    assert art["format"] == "csv"
    assert art["status"] == "PARTIALLY_RECOVERED"
    assert art["status"] != "FULLY_RECOVERED"
    assert art["provenance"]["verified_bytes"] == 289
    assert art["provenance"]["reconstructed_bytes"] == 0
    assert art["provenance"]["missing_bytes"] == 57
    assert art["provenance"]["validation_status"] == "PASSED"


# ── Scenario E: JSON (Not Sent Through CSV Validator) ───────────────

def test_pipeline_a_json_recovery():
    """Scenario E: JSON evidence is routed to canonical JSON engine, not misrouted to CSV."""
    case = store.create_case("Case JSON")
    truncated_json = b'{"case_id": "case_101", "records": [1, 2, 3], "status": "active"'
    store.add_evidence(case.case_id, "report.json", truncated_json)

    res = client.post(f"/api/cases/{case.case_id}/analyze")
    assert res.status_code == 200
    data = res.json()
    assert data["artifact_count"] >= 1

    art = data["artifacts"][0]
    assert art["format"] == "json"
    assert art["format"] != "csv"
    assert art["status"] == "PARTIALLY_RECOVERED"
    assert art["provenance"]["reconstructed_bytes"] > 0


# ── Scenario F: Damaged PDF (Canonical PDF Xref Repair) ──────────────

def test_pipeline_a_damaged_pdf_reconstruction():
    """Scenario F: Damaged PDF with corrupt xref uses canonical PDF xref reconstruction."""
    case = store.create_case("Case Damaged PDF")
    pdf_bytes = build_minimal_pdf()
    corrupt_xref_no_end = pdf_bytes.replace(b"xref", b"xxxx")[:-7]
    store.add_evidence(case.case_id, "document.pdf", corrupt_xref_no_end)

    res = client.post(f"/api/cases/{case.case_id}/analyze")
    assert res.status_code == 200
    data = res.json()
    assert data["artifact_count"] == 1

    art = data["artifacts"][0]
    assert art["format"] == "pdf"
    assert art["provenance"]["validation_status"] == "PASSED"
    assert art["status"] == "PARTIALLY_RECOVERED"


# ── Scenario G: Bifragment Evidence & Ambiguity Preservation ─────────

def test_pipeline_a_bifragment_ambiguity_preservation():
    """Scenario G: Ambiguous bifragment evidence preserves gap ambiguity in canonical pipeline."""
    case = store.create_case("Case Ambiguous Bifragment")
    frag_a = b"First line of log\nSecond line of log\n"
    frag_b = b"Third line of log\nFourth line of log\n"
    gap = b"\x00" * 32
    content = frag_a + gap + frag_b
    store.add_evidence(case.case_id, "syslog.txt", content)

    res = client.post(f"/api/cases/{case.case_id}/analyze")
    assert res.status_code == 200
    data = res.json()
    assert data["artifact_count"] >= 1

    art = data["artifacts"][0]
    assert art["status"] == "PARTIALLY_RECOVERED"
    assert art["status"] != "FULLY_RECOVERED"
    assert art["provenance"]["missing_bytes"] > 0


# ── Scenario H: Multi-Candidate Evidence ────────────────────────────

def test_pipeline_a_multi_candidate_evidence():
    """Scenario H: Multi-candidate container recovers multiple distinct artifacts."""
    case = store.create_case("Case Multi Candidate")
    cand1 = SYNTHETIC_START_MARKER + b"FORMAT=txt\nfilename: log1.txt\nalpha log data\n" + SYNTHETIC_END_MARKER
    cand2 = SYNTHETIC_START_MARKER + b"FORMAT=txt\nfilename: log2.txt\nbeta log data\n" + SYNTHETIC_END_MARKER
    container = cand1 + (b"\x00" * 64) + cand2
    store.add_evidence(case.case_id, "disk.img", container)

    res = client.post(f"/api/cases/{case.case_id}/analyze")
    assert res.status_code == 200
    data = res.json()
    assert data["artifact_count"] == 2
    assert len(data["artifacts"]) == 2

    art1, art2 = data["artifacts"]
    assert art1["artifact_id"] != art2["artifact_id"]
    assert art1["metadata"]["run_id"] != art2["metadata"]["run_id"]
    assert "run_id" in art1["metadata"]
    assert "run_id" in art2["metadata"]


# ── Scenario I: Approach C Run Linkage & Zero Run Duplication ───────

def test_pipeline_a_approach_c_linkage_and_single_persistence():
    """Scenario I: Approach C establishes artifact_id -> run_id linkage with exactly one RecoveryRun."""
    case = store.create_case("Case Linkage Test")
    payload = SYNTHETIC_START_MARKER + b"FORMAT=txt\nHeader: Linkage\nBody: Test linkage\n" + SYNTHETIC_END_MARKER
    store.add_evidence(case.case_id, "evidence.img", payload)

    initial_runs = len(store.list_recovery_runs())
    assert initial_runs == 0

    res = client.post(f"/api/cases/{case.case_id}/analyze")
    assert res.status_code == 200
    data = res.json()
    assert data["artifact_count"] == 1
    art = data["artifacts"][0]
    artifact_id = art["artifact_id"]
    expected_run_id = art["metadata"]["run_id"]

    # Verify exactly ONE RecoveryRun was persisted
    all_runs = store.list_recovery_runs()
    assert len(all_runs) == 1
    assert all_runs[0].run_id == expected_run_id

    # Verify store.get_recovery_run_by_artifact resolves the canonical run
    linked_run = store.get_recovery_run_by_artifact(artifact_id)
    assert linked_run is not None
    assert linked_run.run_id == expected_run_id


# ── Scenario J: Download Parity ─────────────────────────────────────

def test_pipeline_a_download_parity():
    """Scenario J: Download endpoint serves exact extracted payload bytes."""
    case = store.create_case("Case Download Test")
    payload = SYNTHETIC_START_MARKER + b"FORMAT=txt\nHeader: Download\nBody: Byte exact parity\n" + SYNTHETIC_END_MARKER
    store.add_evidence(case.case_id, "evidence.img", payload)

    res = client.post(f"/api/cases/{case.case_id}/analyze")
    art_id = res.json()["artifacts"][0]["artifact_id"]

    # Query download endpoint
    dl_res = client.get(f"/api/artifacts/{art_id}/download")
    assert dl_res.status_code == 200
    assert dl_res.content == payload


# ── Scenario K: Explain Route Resolution ────────────────────────────

def test_pipeline_a_explain_route_resolution():
    """Scenario K: /api/artifacts/{artifact_id}/explain resolves the recovered artifact."""
    case = store.create_case("Case Explain Test")
    payload = SYNTHETIC_START_MARKER + b"FORMAT=txt\nfilename: evidence_audit.txt\nAudit log verified.\n" + SYNTHETIC_END_MARKER
    store.add_evidence(case.case_id, "audit.txt", payload)

    res = client.post(f"/api/cases/{case.case_id}/analyze")
    art_id = res.json()["artifacts"][0]["artifact_id"]

    explain_res = client.post(f"/api/artifacts/{art_id}/explain")
    assert explain_res.status_code == 200
    expl = explain_res.json()
    assert "summary" in expl
    assert "assessment" in expl
    assert expl["facts"]["format"] == "txt"
    assert expl["facts"]["status"] == "FULLY_RECOVERED"


# ── Scenario L: Fault Isolation ─────────────────────────────────────

def test_pipeline_a_fault_isolation():
    """Scenario L: Unexpected candidate failure does not abort recovery of remaining candidates."""
    case = store.create_case("Case Fault Isolation")
    # Candidate 1: valid intact artifact
    cand1 = SYNTHETIC_START_MARKER + b"FORMAT=txt\nvalid text artifact content\n" + SYNTHETIC_END_MARKER
    # Candidate 2: malformed synthetic artifact
    cand2 = SYNTHETIC_START_MARKER + b"\xff\xfe\x00\x01\x02\x03corrupted_bytes"
    container = cand1 + (b"\x00" * 32) + cand2
    store.add_evidence(case.case_id, "mixed.img", container)

    res = client.post(f"/api/cases/{case.case_id}/analyze")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "COMPLETED"
    assert data["artifact_count"] >= 1
    # First artifact must be successfully recovered despite candidate 2 anomalies
    assert any(a["status"] == "FULLY_RECOVERED" for a in data["artifacts"])
