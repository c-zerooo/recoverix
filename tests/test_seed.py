import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_seeded_case_endpoints():
    """Ensure the seeded case_001 and its artifacts/groundtruth never throw 500."""
    res_case = client.get("/api/cases/case_001")
    assert res_case.status_code == 200, f"case_001 failed: {res_case.text}"

    res_artifacts = client.get("/api/cases/case_001/artifacts")
    assert res_artifacts.status_code == 200, f"artifacts failed: {res_artifacts.text}"
    
    res_gt = client.get("/api/cases/case_001/groundtruth")
    assert res_gt.status_code == 200, f"groundtruth failed: {res_gt.text}"
