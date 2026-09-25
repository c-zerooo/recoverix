"""
test_file_recovery.py — Integration test suite for single-file recovery and download endpoints.
"""

import io
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.store import store
from backend.app.recovery.signatures import (
    SYNTHETIC_START_MARKER,
    SYNTHETIC_END_MARKER,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_store():
    store.clear()
    yield
    store.clear()


def test_recover_single_file_success_txt():
    """Test recovering a single TXT file with synthetic markers."""
    payload = SYNTHETIC_START_MARKER + b"FORMAT=txt\nHeader: Test\nBody: Hello Single File Recovery\n" + SYNTHETIC_END_MARKER

    response = client.post(
        "/api/recover-file",
        files={"file": ("damaged_sample.txt", payload, "text/plain")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["original_filename"] == "damaged_sample.txt"
    assert data["recovered_filename"] == "recovered_damaged_sample.txt"
    assert data["format"] == "txt"
    assert data["status"] == "FULLY_RECOVERED"
    assert data["confidence_score"] == 100.0
    assert data["is_downloadable"] is True
    assert "download_url" in data
    assert "Hello Single File Recovery" in (data["content_preview"] or "")


def test_recover_single_file_download_exact_bytes():
    """Test downloading the recovered file buffer and asserting exact byte equality."""
    expected_recovered = SYNTHETIC_START_MARKER + b"FORMAT=txt\nHeader: Test\nBody: Exact Bytes Test\n" + SYNTHETIC_END_MARKER
    evidence_with_padding = b"PADDING_BEFORE" + expected_recovered + b"PADDING_AFTER"

    response = client.post(
        "/api/recover-file",
        files={"file": ("evidence.bin", evidence_with_padding, "application/octet-stream")},
    )

    assert response.status_code == 200
    data = response.json()
    file_id = data["file_id"]
    download_url = data["download_url"]

    # Perform byte download
    dl_response = client.get(download_url)
    assert dl_response.status_code == 200
    assert dl_response.headers["content-type"] == "application/octet-stream"
    assert "attachment; filename=\"recovered_evidence.bin\"" in dl_response.headers["content-disposition"]
    assert dl_response.content == expected_recovered


def test_recover_single_file_unrecoverable():
    """Test uploading random unrecoverable corrupt bytes."""
    corrupt_bytes = b"\x00\x99\xff\xfe\xdc\xba\x88\x77\x66\x55\x44"

    response = client.post(
        "/api/recover-file",
        files={"file": ("corrupt.raw", corrupt_bytes, "application/octet-stream")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "UNRECOVERABLE"
    assert data["confidence_score"] == 0.0
    assert data["is_downloadable"] is False
    assert data["verified_bytes"] == 0


def test_recover_single_file_download_unrecoverable_404():
    """Test downloading an unrecoverable file ID returns 404."""
    corrupt_bytes = b"\x00\x99\xff\xfe\xdc\xba"

    response = client.post(
        "/api/recover-file",
        files={"file": ("corrupt.raw", corrupt_bytes, "application/octet-stream")},
    )

    data = response.json()
    file_id = data["file_id"]

    dl_response = client.get(f"/api/recover-file/{file_id}/download")
    assert dl_response.status_code == 404


def test_recover_single_file_empty_400():
    """Test uploading an empty file returns 400 Bad Request."""
    response = client.post(
        "/api/recover-file",
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "EMPTY_FILE"


def test_recover_single_file_too_large_400():
    """Test uploading a file larger than 5 MB returns 400 Bad Request."""
    oversized = b"A" * (5 * 1024 * 1024 + 1)
    response = client.post(
        "/api/recover-file",
        files={"file": ("large.txt", oversized, "text/plain")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "FILE_TOO_LARGE"


def test_download_case_artifact():
    """Test downloading a case artifact directly via /api/artifacts/{artifact_id}/download."""
    case_resp = client.post("/api/cases", json={"name": "Case Download Test"}).json()
    case_id = case_resp["case_id"]

    artifact_payload = SYNTHETIC_START_MARKER + b"FORMAT=txt\nHeader: Case\nBody: Artifact Download\n" + SYNTHETIC_END_MARKER
    client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("evidence.img", artifact_payload, "application/octet-stream")},
    )

    analysis_res = client.post(f"/api/cases/{case_id}/analyze").json()
    assert analysis_res["artifact_count"] >= 1
    artifact_id = analysis_res["artifacts"][0]["artifact_id"]

    dl_res = client.get(f"/api/artifacts/{artifact_id}/download")
    assert dl_res.status_code == 200
    assert dl_res.content == artifact_payload
