"""
test_api.py — Comprehensive tests for Task 8 FastAPI foundation and shared API contract.

Covers all 23 required test scenarios:
1. GET /health check endpoint (200 OK)
2. POST /api/cases success (201 Created)
3. POST /api/cases empty or invalid name rejection (400 Bad Request)
4. POST /api/cases invalid JSON body handling (422 / 400)
5. GET /api/cases/{case_id} success (200 OK)
6. GET /api/cases/{case_id} non-existent (404 Not Found)
7. POST /api/cases/{case_id}/evidence multipart file upload success (200 OK)
8. POST /api/cases/{case_id}/evidence raw body byte upload success (200 OK)
9. POST /api/cases/{case_id}/evidence empty payload rejection (400 Bad Request)
10. POST /api/cases/{case_id}/evidence > 5 MiB size limit rejection (413 Payload Too Large)
11. POST /api/cases/{case_id}/evidence non-existent case (404 Not Found)
12. POST /api/cases/{case_id}/analyze pipeline execution success (200 OK)
13. POST /api/cases/{case_id}/analyze non-existent case (404 Not Found)
14. POST /api/cases/{case_id}/analyze missing evidence rejection (400 Bad Request)
15. GET /api/cases/{case_id}/artifacts list success (200 OK)
16. GET /api/cases/{case_id}/artifacts non-existent case (404 Not Found)
17. GET /api/artifacts/{artifact_id} detail success (200 OK)
18. GET /api/artifacts/{artifact_id} non-existent artifact (404 Not Found)
19. Seed-42 synthetic evidence full API pipeline end-to-end integration
20. Contract validation: null placeholders present (category=None, priority=None, ai_summary=None)
21. Contract validation: confidence score breakdown schema (5 dimensions + total)
22. Contract validation: forensic provenance schema (byte accounting + method + status)
23. In-memory store test state isolation
"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Ensure imports work from the project root.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.app.main import app
from backend.app.store import store, MAX_EVIDENCE_SIZE
from backend.generate_case import generate_evidence


@pytest.fixture(autouse=True)
def reset_store():
    """Reset the in-memory store before each test."""
    store.clear()
    yield
    store.clear()


client = TestClient(app)


# ── 1. Health Check ─────────────────────────────────────────────────

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "recoverix-api"


# ── 2. Create Case Success ──────────────────────────────────────────

def test_create_case_success():
    payload = {"name": "Forensic Case Alpha", "description": "Investigation of disk image"}
    response = client.post("/api/cases", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Forensic Case Alpha"
    assert data["description"] == "Investigation of disk image"
    assert "case_id" in data
    assert data["case_id"].startswith("case_")
    assert "created_at" in data
    assert data["evidence"] is None
    assert data["artifact_count"] == 0


# ── 3. Create Case Empty Name Rejection ──────────────────────────────

def test_create_case_empty_name():
    # Empty string name
    response = client.post("/api/cases", json={"name": ""})
    assert response.status_code == 400

    # Whitespace name
    response2 = client.post("/api/cases", json={"name": "   "})
    assert response2.status_code == 400


# ── 4. Create Case Invalid JSON Payload ──────────────────────────────

def test_create_case_invalid_payload():
    response = client.post("/api/cases", json={})
    assert response.status_code in (400, 422)


# ── 5. Get Case Success ─────────────────────────────────────────────

def test_get_case_success():
    create_res = client.post("/api/cases", json={"name": "Case Beta"})
    case_id = create_res.json()["case_id"]

    response = client.get(f"/api/cases/{case_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == case_id
    assert data["name"] == "Case Beta"


# ── 6. Get Case Not Found ───────────────────────────────────────────

def test_get_case_not_found():
    response = client.get("/api/cases/non_existent_case_999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ── 7. Upload Evidence Multipart Success ─────────────────────────────

def test_upload_evidence_multipart_success():
    create_res = client.post("/api/cases", json={"name": "Upload Case"})
    case_id = create_res.json()["case_id"]

    evidence_content = b"[SYNTHETIC_ARTIFACT_START]\nfilename: test.txt\nhello world\n[SYNTHETIC_ARTIFACT_END]"
    files = {"file": ("evidence.img", evidence_content, "application/octet-stream")}

    response = client.post(f"/api/cases/{case_id}/evidence", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["evidence"] is not None
    assert data["evidence"]["filename"] == "evidence.img"
    assert data["evidence"]["file_size"] == len(evidence_content)
    assert "sha256" in data["evidence"]


# ── 8. Upload Evidence Raw Body Success ──────────────────────────────

def test_upload_evidence_raw_bytes_success():
    create_res = client.post("/api/cases", json={"name": "Raw Case"})
    case_id = create_res.json()["case_id"]

    evidence_content = b"[SYNTHETIC_ARTIFACT_START]\nfilename: raw.txt\ndata\n[SYNTHETIC_ARTIFACT_END]"

    response = client.post(
        f"/api/cases/{case_id}/evidence",
        content=evidence_content,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["evidence"] is not None
    assert data["evidence"]["file_size"] == len(evidence_content)


# ── 9. Upload Evidence Empty Rejection ──────────────────────────────

def test_upload_evidence_empty_rejection():
    create_res = client.post("/api/cases", json={"name": "Empty Upload Case"})
    case_id = create_res.json()["case_id"]

    # Empty file
    files = {"file": ("empty.img", b"", "application/octet-stream")}
    response = client.post(f"/api/cases/{case_id}/evidence", files=files)
    assert response.status_code == 400


# ── 10. Upload Evidence Oversized Rejection ─────────────────────────

def test_upload_evidence_oversized_rejection():
    create_res = client.post("/api/cases", json={"name": "Large Case"})
    case_id = create_res.json()["case_id"]

    # Exceed 5 MiB by 1 byte
    large_bytes = b"X" * (MAX_EVIDENCE_SIZE + 1)
    files = {"file": ("large.img", large_bytes, "application/octet-stream")}

    response = client.post(f"/api/cases/{case_id}/evidence", files=files)
    assert response.status_code == 413
    assert "exceeds" in response.json()["detail"].lower() or "5 mib" in response.json()["detail"].lower()


# ── 11. Upload Evidence Case Not Found ──────────────────────────────

def test_upload_evidence_case_not_found():
    files = {"file": ("test.img", b"data", "application/octet-stream")}
    response = client.post("/api/cases/invalid_case_id/evidence", files=files)
    assert response.status_code == 404


# ── 12. Analyze Case Success ────────────────────────────────────────

def test_analyze_case_success():
    create_res = client.post("/api/cases", json={"name": "Analyze Case"})
    case_id = create_res.json()["case_id"]

    evidence_content = (
        b"[SYNTHETIC_ARTIFACT_START]\nfilename: doc.txt\nsample text data\n[SYNTHETIC_ARTIFACT_END]"
    )
    client.post(f"/api/cases/{case_id}/evidence", files={"file": ("doc.txt", evidence_content, "text/plain")})

    response = client.post(f"/api/cases/{case_id}/analyze")
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == case_id
    assert data["status"] == "COMPLETED"
    assert data["artifact_count"] >= 1
    assert len(data["artifacts"]) >= 1

    art = data["artifacts"][0]
    assert art["case_id"] == case_id
    assert art["confidence_score"] == 100
    assert art["status"] == "FULLY_RECOVERED"


# ── 13. Analyze Case Not Found ──────────────────────────────────────

def test_analyze_case_not_found():
    response = client.post("/api/cases/non_existent_case_123/analyze")
    assert response.status_code == 404


# ── 14. Analyze Case Missing Evidence ──────────────────────────────

def test_analyze_case_no_evidence():
    create_res = client.post("/api/cases", json={"name": "No Evidence Case"})
    case_id = create_res.json()["case_id"]

    response = client.post(f"/api/cases/{case_id}/analyze")
    assert response.status_code == 400
    assert "no evidence" in response.json()["detail"].lower()


# ── 15. Get Case Artifacts Success ──────────────────────────────────

def test_get_case_artifacts_success():
    create_res = client.post("/api/cases", json={"name": "Artifact List Case"})
    case_id = create_res.json()["case_id"]

    evidence_content = (
        b"[SYNTHETIC_ARTIFACT_START]\na,b\n1,2\n[SYNTHETIC_ARTIFACT_END]"
    )
    client.post(f"/api/cases/{case_id}/evidence", files={"file": ("doc.csv", evidence_content, "text/csv")})
    client.post(f"/api/cases/{case_id}/analyze")

    response = client.get(f"/api/cases/{case_id}/artifacts")
    assert response.status_code == 200
    artifacts = response.json()
    assert isinstance(artifacts, list)
    assert len(artifacts) >= 1
    assert artifacts[0]["format"] == "csv"


# ── 16. Get Case Artifacts Not Found ────────────────────────────────

def test_get_case_artifacts_not_found():
    response = client.get("/api/cases/non_existent_case_000/artifacts")
    assert response.status_code == 404


# ── 17. Get Artifact Detail Success ─────────────────────────────────

def test_get_artifact_detail_success():
    create_res = client.post("/api/cases", json={"name": "Detail Case"})
    case_id = create_res.json()["case_id"]

    evidence_content = (
        b"[SYNTHETIC_ARTIFACT_START]\nfilename: detail.txt\ncontent\n[SYNTHETIC_ARTIFACT_END]"
    )
    client.post(f"/api/cases/{case_id}/evidence", files={"file": ("detail.txt", evidence_content, "text/plain")})
    analyze_res = client.post(f"/api/cases/{case_id}/analyze")
    artifact_id = analyze_res.json()["artifacts"][0]["artifact_id"]

    response = client.get(f"/api/artifacts/{artifact_id}")
    assert response.status_code == 200
    art = response.json()
    assert art["artifact_id"] == artifact_id
    assert art["case_id"] == case_id
    assert art["format"] == "txt"
    assert "confidence_score" in art
    assert "score_breakdown" in art
    assert "provenance" in art


# ── 18. Get Artifact Detail Not Found ───────────────────────────────

def test_get_artifact_detail_not_found():
    response = client.get("/api/artifacts/non_existent_art_999")
    assert response.status_code == 404


# ── 19. Seed-42 End-to-End API Pipeline Integration ─────────────────

def test_seed_42_end_to_end_api_pipeline(tmp_path):
    """Full API integration test using synthetic evidence generated with seed 42."""
    generate_evidence(42, tmp_path)
    img_bytes = (tmp_path / "damaged.img").read_bytes()

    # 1. Create Case
    create_res = client.post("/api/cases", json={"name": "Seed 42 Case", "description": "Synthetic benchmark"})
    assert create_res.status_code == 201
    case_id = create_res.json()["case_id"]

    # 2. Upload Evidence
    upload_res = client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("damaged.img", img_bytes, "application/octet-stream")},
    )
    assert upload_res.status_code == 200
    assert upload_res.json()["evidence"]["file_size"] == len(img_bytes)

    # 3. Analyze Case
    analyze_res = client.post(f"/api/cases/{case_id}/analyze")
    assert analyze_res.status_code == 200
    analysis_data = analyze_res.json()
    assert analysis_data["artifact_count"] >= 1
    artifacts = analysis_data["artifacts"]

    # 4. List Case Artifacts
    list_res = client.get(f"/api/cases/{case_id}/artifacts")
    assert list_res.status_code == 200
    assert len(list_res.json()) == len(artifacts)

    # 5. Retrieve Individual Artifact
    first_art_id = artifacts[0]["artifact_id"]
    art_res = client.get(f"/api/artifacts/{first_art_id}")
    assert art_res.status_code == 200
    art = art_res.json()
    assert art["artifact_id"] == first_art_id
    assert art["case_id"] == case_id


# ── 20. Shared API Contract: Explicit Null Placeholders ──────────────

def test_contract_null_placeholders():
    create_res = client.post("/api/cases", json={"name": "Null Placeholder Case"})
    case_id = create_res.json()["case_id"]

    evidence_content = (
        b"[SYNTHETIC_ARTIFACT_START]\nfilename: test.txt\ndata\n[SYNTHETIC_ARTIFACT_END]"
    )
    client.post(f"/api/cases/{case_id}/evidence", files={"file": ("test.txt", evidence_content, "text/plain")})
    analyze_res = client.post(f"/api/cases/{case_id}/analyze")
    art = analyze_res.json()["artifacts"][0]

    # Explicit null placeholders required by Recoverix API contract
    assert "category" in art
    assert art["category"] is None

    assert "priority" in art
    assert art["priority"] is None

    assert "ai_summary" in art
    assert art["ai_summary"] is None


# ── 21. Shared API Contract: Score Breakdown Schema ──────────────────

def test_contract_score_breakdown_schema():
    create_res = client.post("/api/cases", json={"name": "Score Breakdown Case"})
    case_id = create_res.json()["case_id"]

    evidence_content = (
        b"[SYNTHETIC_ARTIFACT_START]\nfilename: test.txt\ndata\n[SYNTHETIC_ARTIFACT_END]"
    )
    client.post(f"/api/cases/{case_id}/evidence", files={"file": ("test.txt", evidence_content, "text/plain")})
    analyze_res = client.post(f"/api/cases/{case_id}/analyze")
    art = analyze_res.json()["artifacts"][0]

    bd = art["score_breakdown"]
    assert "header_validity" in bd
    assert "footer_validity" in bd
    assert "structural_validation" in bd
    assert "size_plausibility" in bd
    assert "reconstruction_integrity" in bd
    assert "total" in bd

    assert bd["total"] == bd["header_validity"] + bd["footer_validity"] + bd["structural_validation"] + bd["size_plausibility"] + bd["reconstruction_integrity"]


# ── 22. Shared API Contract: Forensic Provenance Schema ─────────────

def test_contract_provenance_schema():
    create_res = client.post("/api/cases", json={"name": "Provenance Case"})
    case_id = create_res.json()["case_id"]

    evidence_content = (
        b"[SYNTHETIC_ARTIFACT_START]\nfilename: test.txt\ndata\n[SYNTHETIC_ARTIFACT_END]"
    )
    client.post(f"/api/cases/{case_id}/evidence", files={"file": ("test.txt", evidence_content, "text/plain")})
    analyze_res = client.post(f"/api/cases/{case_id}/analyze")
    art = analyze_res.json()["artifacts"][0]

    prov = art["provenance"]
    assert "verified_bytes" in prov
    assert "reconstructed_bytes" in prov
    assert "missing_bytes" in prov
    assert "reconstruction_method" in prov
    assert "validation_status" in prov

    assert prov["validation_status"] in ("PASSED", "FAILED")


# ── 23. In-Memory Store Test Isolation ───────────────────────────────

def test_in_memory_store_isolation():
    client.post("/api/cases", json={"name": "Isolation Case 1"})
    assert len(store.list_cases()) == 1

    store.clear()
    assert len(store.list_cases()) == 0


# ── 24. Task 2 Ingestion Reuse Verification ──────────────────────────

def test_task2_ingestion_reuse_in_store_and_api():
    from backend.app.ingestion import compute_metadata

    create_res = client.post("/api/cases", json={"name": "Ingestion Reuse Case"})
    case_id = create_res.json()["case_id"]

    content = b"Task 2 Ingestion Integration Test Bytes Payload"
    upload_res = client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("test_ingest.img", content, "application/octet-stream")},
    )
    assert upload_res.status_code == 200

    # Verify SHA-256 and size match Task 2 compute_metadata directly
    expected_meta = compute_metadata(content, filename="test_ingest.img")
    ev = upload_res.json()["evidence"]
    assert ev["sha256"] == expected_meta.sha256
    assert ev["file_size"] == expected_meta.size_bytes

    # Verify store chunks created via Task 2 chunking layer
    chunks = store.get_evidence_chunks(case_id)
    assert chunks is not None
    assert len(chunks) == expected_meta.num_chunks
    assert chunks[0].data == content
    assert chunks[0].length == len(content)


# ── 25. CORRUPTED Status Preservation & API Serialization ────────────

def test_corrupted_status_preservation_and_serialization():
    from backend.app.scoring.confidence import classify_recovery_status
    from backend.app.models.confidence import RecoveryStatus
    from backend.app.models.artifact import ArtifactResponse, ConfidenceBreakdownSchema, ArtifactProvenanceSchema

    # Proving score 49 yields CORRUPTED status
    status_49 = classify_recovery_status(score=49, reconstructed_bytes=0, missing_bytes=0)
    assert status_49 == RecoveryStatus.CORRUPTED
    assert status_49.value == "CORRUPTED"

    # Proving API model serialization of CORRUPTED status
    art = ArtifactResponse(
        artifact_id="art_corrupted_test",
        case_id="case_corrupted_test",
        format="txt",
        size_bytes=100,
        confidence_score=49,
        score_breakdown=ConfidenceBreakdownSchema(
            header_validity=20,
            footer_validity=0,
            structural_validation=0,
            size_plausibility=15,
            reconstruction_integrity=14,
            total=49,
        ),
        status=status_49.value,
        provenance=ArtifactProvenanceSchema(
            verified_bytes=100,
            reconstructed_bytes=0,
            missing_bytes=0,
            reconstruction_method="NONE",
            validation_status="FAILED",
        ),
        category=None,
        priority=None,
        ai_summary=None,
        content_preview="[SYNTHETIC_ARTIFACT_START]...",
    )

    dump = art.model_dump()
    assert dump["status"] == "CORRUPTED"
    assert dump["confidence_score"] == 49

