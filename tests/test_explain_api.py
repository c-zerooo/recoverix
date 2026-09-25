import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.store import store
from backend.app.models.artifact import (
    ArtifactResponse, ConfidenceBreakdownSchema, ArtifactProvenanceSchema
)
from backend.app.scoring.explainer import _explanation_cache

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_store():
    store.clear()
    _explanation_cache.clear()
    
    case = store.create_case(name="Test Case")
    
    artifact = ArtifactResponse(
        artifact_id="art_123",
        case_id=case.case_id,
        format="txt",
        size_bytes=1500,
        confidence_score=90,
        score_breakdown=ConfidenceBreakdownSchema(
            header_validity=20, footer_validity=20,
            structural_validation=20, size_plausibility=15,
            reconstruction_integrity=15, total=90
        ),
        status="FULLY_RECOVERED",
        provenance=ArtifactProvenanceSchema(
            verified_bytes=1500, reconstructed_bytes=0,
            missing_bytes=0, reconstruction_method="CONTIGUOUS",
            validation_status="VALID"
        ),
        category="DOCUMENT",
        priority="MEDIUM",
        ai_summary=None,
        content_preview="Hello world",
        metadata={}
    )
    store.add_artifact(artifact)

def test_explain_api():
    response = client.post("/api/artifacts/art_123/explain")
    assert response.status_code == 200
    data = response.json()
    assert data["cached"] is False
    assert "DOCUMENT" in data["summary"]
    
    # Second call should be cached
    response2 = client.post("/api/artifacts/art_123/explain")
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["cached"] is True
