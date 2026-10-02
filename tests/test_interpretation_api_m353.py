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
    """Verify that remaining cluster and case placeholder endpoints return 501 Not Implemented."""
    # Cluster routes (Phase 3.5.3.4)
    res_get_cl = client.get("/api/cases/case_test_01/clusters/cluster_01/interpretation")
    assert res_get_cl.status_code == 501
    assert "3.5.3.4" in res_get_cl.json()["detail"]

    res_post_cl = client.post("/api/cases/case_test_01/clusters/cluster_01/interpretation")
    assert res_post_cl.status_code == 501
    assert "3.5.3.4" in res_post_cl.json()["detail"]

    # Case routes (Phase 3.5.3.5)
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


def test_10_artifact_interpretation_get_and_post_not_found(client: TestClient):
    """TEST 10: GET and POST on non-existent artifact return 404."""
    # GET non-existent
    res_get = client.get("/api/artifacts/non_existent_artifact_xyz/interpretation")
    assert res_get.status_code == 404
    assert "Artifact 'non_existent_artifact_xyz' not found" in res_get.json()["detail"]

    # POST non-existent
    res_post = client.post("/api/artifacts/non_existent_artifact_xyz/interpretation")
    assert res_post.status_code == 404
    assert "Artifact 'non_existent_artifact_xyz' not found" in res_post.json()["detail"]


def test_11_artifact_interpretation_get_not_generated_returns_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """TEST 11: GET existing artifact with ai_summary=None returns 404 with guidance message.

    Verifies:
    - Status is 404.
    - Message directs caller to POST: "Interpretation not generated for artifact '{artifact_id}'. Call POST to generate."
    - Zero provider invocations.
    - Zero SQLite mutations (ai_summary remains None).
    """
    from backend.app.store import store
    from backend.app.scoring.interpretation_service import InterpretationService

    def forbid_interpret(*args, **kwargs):
        raise AssertionError("interpret_artifact must NOT be called during GET")

    monkeypatch.setattr(InterpretationService, "interpret_artifact", forbid_interpret)

    case = store.create_case("M353.3 Test 11 Case")
    art = _make_test_artifact("art_test_11_uninterpreted", case.case_id, ai_summary=None)
    store.add_artifact(art)

    res = client.get(f"/api/artifacts/{art.artifact_id}/interpretation")
    assert res.status_code == 404
    assert res.json()["detail"] == f"Interpretation not generated for artifact '{art.artifact_id}'. Call POST to generate."

    # SQLite must remain untouched
    stored = store.get_artifact(art.artifact_id)
    assert stored is not None
    assert stored.ai_summary is None


def test_12_artifact_interpretation_get_persisted_returns_200(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """TEST 12: GET existing artifact with valid persisted JSON returns 200 with cached=True.

    Verifies:
    - Status is 200.
    - Response matches GroundedArtifactInterpretation structure.
    - cached is True.
    - Zero provider invocations.
    - SQLite record remains completely untouched.
    """
    import json
    from backend.app.store import store
    from backend.app.scoring.interpretation_service import InterpretationService
    from backend.app.models.interpretation import (
        GroundedArtifactInterpretation,
        DeterministicArtifactFacts,
        ProviderInterpretationOutput,
    )

    def forbid_interpret(*args, **kwargs):
        raise AssertionError("interpret_artifact must NOT be called when reading persisted interpretation")

    monkeypatch.setattr(InterpretationService, "interpret_artifact", forbid_interpret)

    case = store.create_case("M353.3 Test 12 Case")
    art_id = "art_test_12_persisted"
    facts = DeterministicArtifactFacts(
        artifact_id=art_id,
        filename=f"{art_id}.txt",
        format="txt",
        size_bytes=500,
        status="FULLY_RECOVERED",
        confidence_score=95.0,
        priority="HIGH",
        verified_bytes=500,
        reconstructed_bytes=0,
        missing_bytes=0,
        reconstruction_method="CONTIGUOUS",
        validation_status="PASSED",
    )
    output = ProviderInterpretationOutput(
        summary="Persisted test forensic summary",
        details=["Observation A", "Observation B"],
        assessment="Valid high-integrity document",
        structural_context="Linear text structure",
        limitations="No missing bytes detected",
        recommended_next_steps="Verify with application parser",
    )
    persisted_interp = GroundedArtifactInterpretation(
        facts=facts,
        interpretation=output,
        source="DETERMINISTIC_RULES",
        cached=False,
        generated_at="2026-10-02T12:00:00Z",
    )
    persisted_json = json.dumps(persisted_interp.model_dump())

    art = _make_test_artifact(art_id, case.case_id, ai_summary=persisted_json)
    store.add_artifact(art)

    res = client.get(f"/api/artifacts/{art_id}/interpretation")
    assert res.status_code == 200
    data = res.json()

    # Must validate against GroundedArtifactInterpretation model
    validated = GroundedArtifactInterpretation.model_validate(data)
    assert validated.cached is True
    assert validated.facts.artifact_id == art_id
    assert validated.interpretation.summary == "Persisted test forensic summary"
    assert validated.facts.priority == "HIGH"
    assert validated.source == "DETERMINISTIC_RULES"

    # SQLite must remain identical to persisted_json
    stored = store.get_artifact(art_id)
    assert stored is not None
    assert stored.ai_summary == persisted_json


def test_13_artifact_interpretation_post_generates_and_persists(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """TEST 13: POST existing artifact with ai_summary=None generates fresh interpretation.

    Verifies:
    - Status is 200.
    - Response is valid GroundedArtifactInterpretation with cached=False.
    - Persisted into SQLite artifacts.ai_summary.
    """
    import json
    from backend.app.store import store
    from backend.app.models.interpretation import GroundedArtifactInterpretation

    monkeypatch.setenv("RECOVERIX_OFFLINE", "1")

    case = store.create_case("M353.3 Test 13 Case")
    art_id = "art_test_13_generate"
    art = _make_test_artifact(art_id, case.case_id, ai_summary=None)
    store.add_artifact(art)

    res = client.post(f"/api/artifacts/{art_id}/interpretation")
    assert res.status_code == 200
    data = res.json()

    validated = GroundedArtifactInterpretation.model_validate(data)
    assert validated.cached is False
    assert validated.facts.artifact_id == art_id
    assert validated.source == "DETERMINISTIC_RULES"
    assert len(validated.interpretation.summary) > 0

    # Verify persisted in SQLite
    stored = store.get_artifact(art_id)
    assert stored is not None
    assert stored.ai_summary is not None
    saved_json = json.loads(stored.ai_summary)
    assert saved_json["facts"]["artifact_id"] == art_id
    assert saved_json["interpretation"]["summary"] == validated.interpretation.summary


def test_14_artifact_interpretation_post_reuse_persisted_when_not_forced(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """TEST 14: POST with force_refresh=False reuses persisted interpretation without provider call.

    Verifies:
    - Default force_refresh=False reuses existing valid interpretation.
    - Explicit force_refresh=false query param also reuses existing valid interpretation.
    - Zero provider invocations.
    - cached is True in response.
    - SQLite record remains unmodified.
    """
    import json
    from backend.app.store import store
    from backend.app.scoring.interpretation_service import InterpretationService
    from backend.app.models.interpretation import (
        GroundedArtifactInterpretation,
        DeterministicArtifactFacts,
        ProviderInterpretationOutput,
    )

    def forbid_provider(*args, **kwargs):
        raise AssertionError("Provider must NOT be invoked when force_refresh=False and valid cache exists")

    monkeypatch.setattr(InterpretationService, "_invoke_with_fallback", forbid_provider)

    case = store.create_case("M353.3 Test 14 Case")
    art_id = "art_test_14_reuse"
    facts = DeterministicArtifactFacts(
        artifact_id=art_id,
        filename=f"{art_id}.txt",
        format="txt",
        size_bytes=500,
        status="FULLY_RECOVERED",
        confidence_score=95.0,
        priority="HIGH",
        verified_bytes=500,
        reconstructed_bytes=0,
        missing_bytes=0,
        reconstruction_method="CONTIGUOUS",
        validation_status="PASSED",
    )
    output = ProviderInterpretationOutput(
        summary="Existing cached summary that must not be regenerated",
        details=["Observation 1"],
        assessment="High integrity",
        structural_context="Standard context",
        limitations="None",
        recommended_next_steps="None",
    )
    persisted_interp = GroundedArtifactInterpretation(
        facts=facts,
        interpretation=output,
        source="DETERMINISTIC_RULES",
        cached=False,
        generated_at="2026-10-02T12:00:00Z",
    )
    persisted_json = json.dumps(persisted_interp.model_dump())

    art = _make_test_artifact(art_id, case.case_id, ai_summary=persisted_json)
    store.add_artifact(art)

    # 1. Default POST (force_refresh not specified)
    res_default = client.post(f"/api/artifacts/{art_id}/interpretation")
    assert res_default.status_code == 200
    data_default = res_default.json()
    assert data_default["cached"] is True
    assert data_default["interpretation"]["summary"] == "Existing cached summary that must not be regenerated"

    # 2. Explicit POST with force_refresh=false
    res_param = client.post(f"/api/artifacts/{art_id}/interpretation?force_refresh=false")
    assert res_param.status_code == 200
    data_param = res_param.json()
    assert data_param["cached"] is True
    assert data_param["interpretation"]["summary"] == "Existing cached summary that must not be regenerated"

    # SQLite record must remain unchanged
    stored = store.get_artifact(art_id)
    assert stored is not None
    assert stored.ai_summary == persisted_json


def test_15_artifact_interpretation_post_force_refresh_regenerates(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """TEST 15: POST with force_refresh=True regenerates and replaces persisted interpretation.

    Verifies:
    - Provider is invoked.
    - Response has cached=False and newly generated content.
    - SQLite record is replaced with newly generated interpretation.
    """
    import json
    from backend.app.store import store
    from backend.app.scoring.interpretation_service import InterpretationService
    from backend.app.models.interpretation import (
        GroundedArtifactInterpretation,
        DeterministicArtifactFacts,
        ProviderInterpretationOutput,
    )

    case = store.create_case("M353.3 Test 15 Case")
    art_id = "art_test_15_refresh"
    facts = DeterministicArtifactFacts(
        artifact_id=art_id,
        filename=f"{art_id}.txt",
        format="txt",
        size_bytes=500,
        status="FULLY_RECOVERED",
        confidence_score=95.0,
        priority="HIGH",
        verified_bytes=500,
        reconstructed_bytes=0,
        missing_bytes=0,
        reconstruction_method="CONTIGUOUS",
        validation_status="PASSED",
    )
    old_output = ProviderInterpretationOutput(
        summary="Old outdated interpretation summary",
        details=["Old detail"],
        assessment="Old assessment",
        structural_context="Old context",
        limitations="Old limitations",
        recommended_next_steps="Old next steps",
    )
    old_interp = GroundedArtifactInterpretation(
        facts=facts,
        interpretation=old_output,
        source="DETERMINISTIC_RULES",
        cached=False,
        generated_at="2026-10-01T00:00:00Z",
    )
    old_json = json.dumps(old_interp.model_dump())

    art = _make_test_artifact(art_id, case.case_id, ai_summary=old_json)
    store.add_artifact(art)

    # Mock provider to return distinct updated summary
    def mock_invoke(self, context):
        return ProviderInterpretationOutput(
            summary="Freshly regenerated forensic interpretation summary",
            details=["Fresh observation 1", "Fresh observation 2"],
            assessment="Refreshed forensic assessment",
            structural_context="Refreshed context",
            limitations="Fresh limitations",
            recommended_next_steps="Fresh next steps",
        ), "GEMINI_1_5_FLASH"

    monkeypatch.setattr(InterpretationService, "_invoke_with_fallback", mock_invoke)

    res = client.post(f"/api/artifacts/{art_id}/interpretation?force_refresh=true")
    assert res.status_code == 200
    data = res.json()

    assert data["cached"] is False
    assert data["source"] == "GEMINI_1_5_FLASH"
    assert data["interpretation"]["summary"] == "Freshly regenerated forensic interpretation summary"

    # SQLite must be updated
    stored = store.get_artifact(art_id)
    assert stored is not None
    assert stored.ai_summary is not None
    saved_json = json.loads(stored.ai_summary)
    assert saved_json["interpretation"]["summary"] == "Freshly regenerated forensic interpretation summary"
    assert saved_json["source"] == "GEMINI_1_5_FLASH"


def test_16_artifact_interpretation_get_malformed_returns_controlled_500(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """TEST 16: GET artifact with malformed persisted ai_summary returns controlled 500.

    Verifies:
    - Status is 500.
    - Detail message explains malformed state without leaking tracebacks or secrets.
    - Zero provider invocations.
    - Malformed record in SQLite is NOT silently overwritten.
    """
    from backend.app.store import store
    from backend.app.scoring.interpretation_service import InterpretationService

    def forbid_interpret(*args, **kwargs):
        raise AssertionError("interpret_artifact must NOT be called on malformed GET")

    monkeypatch.setattr(InterpretationService, "interpret_artifact", forbid_interpret)

    case = store.create_case("M353.3 Test 16 Case")
    art_id = "art_test_16_corrupt"
    corrupt_content = "NOT_JSON_OR_CORRUPT_PAYLOAD{{{"
    art = _make_test_artifact(art_id, case.case_id, ai_summary=corrupt_content)
    store.add_artifact(art)

    res = client.get(f"/api/artifacts/{art_id}/interpretation")
    assert res.status_code == 500
    detail = res.json()["detail"]
    assert detail == f"Persisted interpretation for artifact '{art_id}' is malformed or invalid"

    # Database must retain the exact malformed string without overwriting
    stored = store.get_artifact(art_id)
    assert stored is not None
    assert stored.ai_summary == corrupt_content

    # Also test with valid JSON that violates GroundedArtifactInterpretation schema
    art_id_schema_fail = "art_test_16_schema_fail"
    invalid_schema_content = '{"invalid_field": 123, "not_an_interpretation": true}'
    art2 = _make_test_artifact(art_id_schema_fail, case.case_id, ai_summary=invalid_schema_content)
    store.add_artifact(art2)

    res2 = client.get(f"/api/artifacts/{art_id_schema_fail}/interpretation")
    assert res2.status_code == 500
    assert res2.json()["detail"] == f"Persisted interpretation for artifact '{art_id_schema_fail}' is malformed or invalid"

    stored2 = store.get_artifact(art_id_schema_fail)
    assert stored2 is not None
    assert stored2.ai_summary == invalid_schema_content


def test_17_legacy_explain_remains_functional_alongside_new_endpoints(client: TestClient):
    """TEST 17: Legacy POST /api/artifacts/{artifact_id}/explain remains operational alongside new routes.

    Verifies:
    - Legacy route returns 200 with dictionary containing summary, details, priority, facts.
    - New GET /api/artifacts/{id}/interpretation and POST /api/artifacts/{id}/interpretation
      coexist independently.
    """
    from backend.app.store import store

    case = store.create_case("M353.3 Test 17 Case")
    art_id = "art_test_17_legacy_coexist"
    art = _make_test_artifact(art_id, case.case_id, ai_summary=None)
    store.add_artifact(art)

    # 1. Call legacy endpoint
    res_legacy = client.post(f"/api/artifacts/{art_id}/explain")
    assert res_legacy.status_code == 200
    data_legacy = res_legacy.json()
    assert "summary" in data_legacy
    assert "details" in data_legacy
    assert "priority" in data_legacy
    assert "facts" in data_legacy
    assert data_legacy.get("available") is True

    # 2. Call new POST endpoint on the same artifact
    res_post = client.post(f"/api/artifacts/{art_id}/interpretation")
    assert res_post.status_code == 200
    data_post = res_post.json()
    assert data_post["facts"]["artifact_id"] == art_id

    # 3. Call new GET endpoint on the same artifact
    res_get = client.get(f"/api/artifacts/{art_id}/interpretation")
    assert res_get.status_code == 200
    data_get = res_get.json()
    assert data_get["cached"] is True
    assert data_get["facts"]["artifact_id"] == art_id
