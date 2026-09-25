import pytest
from backend.app.scoring.explainer import explain_artifact, _explanation_cache

class MockProvenance:
    verified_bytes = 1000
    reconstructed_bytes = 500
    missing_bytes = 200

class MockArtifact:
    category = "DOCUMENT"
    priority = "HIGH"
    status = "PARTIALLY_RECOVERED"
    confidence_score = 75
    provenance = MockProvenance()

def test_explain_artifact():
    _explanation_cache.clear()
    artifact = MockArtifact()
    
    explanation = explain_artifact("art_1", artifact)
    assert not explanation["cached"]
    assert "Grounded explanation for DOCUMENT" in explanation["summary"]
    
    details = "".join(explanation["details"])
    assert "1000" in details
    assert "500" in details
    assert "200" in details
    assert "PARTIALLY_RECOVERED" in details
    assert "75/100" in details
    
    # Test caching
    explanation2 = explain_artifact("art_1", artifact)
    assert explanation2["cached"]
