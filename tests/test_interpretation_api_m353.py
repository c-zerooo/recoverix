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
