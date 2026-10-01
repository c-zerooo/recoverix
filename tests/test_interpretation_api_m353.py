"""
test_interpretation_api_m353.py — Test suite for Milestone 3.5.3.1 API router setup & contracts.

Verifies:
1. interpretation router imports cleanly.
2. router is properly mounted on FastAPI app under /api prefix.
3. All six route shapes exist with correct HTTP methods and paths.
4. Response models correctly reference canonical 3.5.1 and 3.5.2 Pydantic models.
5. Placeholder handlers return 501 Not Implemented without side effects.
6. Application startup and existing endpoints remain unbroken.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.api.interpretation import router as interpretation_router
from backend.app.models.interpretation import (
    GroundedArtifactInterpretation,
    GroundedClusterInterpretation,
    GroundedCaseInterpretation,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_01_router_import_and_definition():
    """Verify that interpretation router is defined with expected routes."""
    assert interpretation_router is not None
    assert interpretation_router.tags == ["interpretation"]


def test_02_routes_mounted_on_app():
    """Verify all six canonical route shapes are mounted on FastAPI app."""
    expected_routes = {
        ("GET", "/api/artifacts/{artifact_id}/interpretation"),
        ("POST", "/api/artifacts/{artifact_id}/interpretation"),
        ("GET", "/api/cases/{case_id}/clusters/{cluster_id}/interpretation"),
        ("POST", "/api/cases/{case_id}/clusters/{cluster_id}/interpretation"),
        ("GET", "/api/cases/{case_id}/interpretation"),
        ("POST", "/api/cases/{case_id}/interpretation"),
    }

    actual_routes = set()
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                if method in ("GET", "POST"):
                    actual_routes.add((method, route.path))

    for method, path in expected_routes:
        assert (method, path) in actual_routes, f"Missing route: {method} {path}"


def test_03_route_response_models():
    """Verify that the mounted routes declare the canonical response models."""
    route_models = {}
    for route in app.routes:
        if hasattr(route, "path") and hasattr(route, "response_model"):
            route_models[(list(route.methods)[0] if hasattr(route, "methods") else None, route.path)] = route.response_model

    # Check that the routes map to canonical models
    for route in app.routes:
        if hasattr(route, "path") and hasattr(route, "methods"):
            if route.path == "/api/artifacts/{artifact_id}/interpretation":
                assert route.response_model is GroundedArtifactInterpretation
            elif route.path == "/api/cases/{case_id}/clusters/{cluster_id}/interpretation":
                assert route.response_model is GroundedClusterInterpretation
            elif route.path == "/api/cases/{case_id}/interpretation":
                assert route.response_model is GroundedCaseInterpretation


def test_04_placeholder_endpoints_return_501(client: TestClient):
    """Verify that placeholder endpoints return 501 Not Implemented and have no side effects."""
    # Artifact routes
    res_get_art = client.get("/api/artifacts/art_test_01/interpretation")
    assert res_get_art.status_code == 501
    assert "3.5.3.3" in res_get_art.json()["detail"]

    res_post_art = client.post("/api/artifacts/art_test_01/interpretation")
    assert res_post_art.status_code == 501
    assert "3.5.3.3" in res_post_art.json()["detail"]

    # Cluster routes
    res_get_cl = client.get("/api/cases/case_test_01/clusters/cluster_01/interpretation")
    assert res_get_cl.status_code == 501
    assert "3.5.3.4" in res_get_cl.json()["detail"]

    res_post_cl = client.post("/api/cases/case_test_01/clusters/cluster_01/interpretation")
    assert res_post_cl.status_code == 501
    assert "3.5.3.4" in res_post_cl.json()["detail"]

    # Case routes
    res_get_case = client.get("/api/cases/case_test_01/interpretation")
    assert res_get_case.status_code == 501
    assert "3.5.3.5" in res_get_case.json()["detail"]

    res_post_case = client.post("/api/cases/case_test_01/interpretation")
    assert res_post_case.status_code == 501
    assert "3.5.3.5" in res_post_case.json()["detail"]


def test_05_health_check_and_existing_app_unaffected(client: TestClient):
    """Verify app health check and startup remain completely valid."""
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "service": "recoverix-api"}


def _make_test_artifact(
    artifact_id: str, case_id: str, ai_summary: str | None = None
) -> ArtifactResponse:
    from backend.app.models.artifact import (
        ArtifactResponse,
        ConfidenceBreakdownSchema,
        ArtifactProvenanceSchema,
    )

    return ArtifactResponse(
        artifact_id=artifact_id,
        case_id=case_id,
        format="txt",
        size_bytes=500,
        confidence_score=95,
        score_breakdown=ConfidenceBreakdownSchema(
            header_validity=20,
            footer_validity=20,
            structural_validation=25,
            size_plausibility=15,
            reconstruction_integrity=15,
            total=95,
        ),
        status="FULLY_RECOVERED",
        provenance=ArtifactProvenanceSchema(
            verified_bytes=500,
            reconstructed_bytes=0,
            missing_bytes=0,
            reconstruction_method="CONTIGUOUS",
            validation_status="PASSED",
        ),
        category="DOCUMENT",
        priority="HIGH",
        ai_summary=ai_summary,
        content_preview="Forensic test artifact content preview",
        metadata={},
    )


def test_06_artifact_get_has_no_interpretation_side_effect(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """TEST A: GET /api/artifacts/{id} must not generate interpretation or write SQLite."""
    from backend.app.store import store
    from backend.app.scoring.interpretation_service import InterpretationService

    def forbid_explain(*args, **kwargs):
        raise AssertionError("explain_artifact must NOT be called during GET /api/artifacts/{id}")

    def forbid_interpret(*args, **kwargs):
        raise AssertionError("interpret_artifact must NOT be called during GET /api/artifacts/{id}")

    monkeypatch.setattr("backend.app.api.artifacts.explain_artifact", forbid_explain)
    monkeypatch.setattr(InterpretationService, "interpret_artifact", forbid_interpret)

    case = store.create_case("GET Side Effect Test Case A")
    art = _make_test_artifact("art_side_effect_01", case.case_id, ai_summary=None)
    store.add_artifact(art)

    # Initial state in DB
    db_art_before = store.get_artifact("art_side_effect_01")
    assert db_art_before is not None
    assert db_art_before.ai_summary is None

    # Call GET endpoint
    res = client.get("/api/artifacts/art_side_effect_01")
    assert res.status_code == 200
    data = res.json()
    assert data["artifact_id"] == "art_side_effect_01"
    assert data["ai_summary"] is None

    # Database state must remain unchanged
    db_art_after = store.get_artifact("art_side_effect_01")
    assert db_art_after is not None
    assert db_art_after.ai_summary is None


def test_07_case_artifacts_get_has_no_interpretation_side_effect(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """TEST B: GET /api/cases/{case_id}/artifacts must not generate interpretation or write SQLite."""
    from backend.app.store import store
    from backend.app.scoring.interpretation_service import InterpretationService

    def forbid_explain(*args, **kwargs):
        raise AssertionError("explain_artifact must NOT be called during GET /api/cases/{case_id}/artifacts")

    def forbid_interpret(*args, **kwargs):
        raise AssertionError("interpret_artifact must NOT be called during GET /api/cases/{case_id}/artifacts")

    monkeypatch.setattr("backend.app.api.artifacts.explain_artifact", forbid_explain)
    monkeypatch.setattr(InterpretationService, "interpret_artifact", forbid_interpret)

    case = store.create_case("GET Side Effect Test Case B")
    art = _make_test_artifact("art_side_effect_02", case.case_id, ai_summary=None)
    store.add_artifact(art)

    res = client.get(f"/api/cases/{case.case_id}/artifacts")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 1
    target = next((a for a in data if a["artifact_id"] == "art_side_effect_02"), None)
    assert target is not None
    assert target["ai_summary"] is None

    # Database state must remain unchanged
    db_art = store.get_artifact("art_side_effect_02")
    assert db_art is not None
    assert db_art.ai_summary is None


def test_08_persisted_interpretation_is_only_read_on_get(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """TEST C: Existing persisted interpretation is returned as-is without regeneration."""
    import json
    from backend.app.store import store
    from backend.app.scoring.interpretation_service import InterpretationService

    def forbid_explain(*args, **kwargs):
        raise AssertionError("explain_artifact must NOT be called when reading persisted interpretation")

    def forbid_interpret(*args, **kwargs):
        raise AssertionError("interpret_artifact must NOT be called when reading persisted interpretation")

    monkeypatch.setattr("backend.app.api.artifacts.explain_artifact", forbid_explain)
    monkeypatch.setattr(InterpretationService, "interpret_artifact", forbid_interpret)

    persisted_summary = json.dumps({
        "summary": "Existing persisted forensic summary",
        "details": ["Pre-existing observation 1"],
        "cached": True,
    })

    case = store.create_case("GET Persisted Read Test Case C")
    art = _make_test_artifact("art_side_effect_03", case.case_id, ai_summary=persisted_summary)
    store.add_artifact(art)

    res = client.get("/api/artifacts/art_side_effect_03")
    assert res.status_code == 200
    data = res.json()
    assert data["ai_summary"] == persisted_summary

    # Database state must remain exactly identical
    db_art = store.get_artifact("art_side_effect_03")
    assert db_art is not None
    assert db_art.ai_summary == persisted_summary


def test_09_legacy_explicit_explain_remains_functional(client: TestClient):
    """TEST D: Legacy POST /api/artifacts/{id}/explain remains fully operational."""
    from backend.app.store import store

    case = store.create_case("Legacy Explain Test Case D")
    art = _make_test_artifact("art_legacy_explain_01", case.case_id, ai_summary=None)
    store.add_artifact(art)

    res = client.post("/api/artifacts/art_legacy_explain_01/explain")
    assert res.status_code == 200
    data = res.json()
    assert "summary" in data
    assert "details" in data
    assert "priority" in data
    assert "facts" in data
    assert data.get("available") is True
