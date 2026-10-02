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
    """Verify that remaining case placeholder endpoints return 501 Not Implemented."""
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


def _make_test_recovery_run(
    run_id: str,
    case_id: str,
    format: str = "json",
    evidence_start: int = 0,
    evidence_end: Optional[int] = 500,
    evidence_file_id: Optional[str] = "ev_01",
    verified_bytes: int = 500,
    reconstructed_bytes: int = 0,
    missing_bytes: int = 0,
    detection_method: str = "magic_bytes",
    status: str = "FULLY_RECOVERED",
    confidence_score: float = 95.0,
    filename: str = "evidence.bin",
):
    from datetime import datetime, timezone
    from backend.app.models.recovery_run import RecoveryRun

    prov = {
        "evidence_start": evidence_start,
        "coordinate_system": (
            "physical_evidence_offsets"
            if evidence_end is not None
            else "whole_buffer_fallback"
        ),
        "detection_method": detection_method,
        "case_id": case_id,
    }
    if evidence_end is not None:
        prov["evidence_end"] = evidence_end
    if evidence_file_id is not None:
        prov["evidence_file_id"] = evidence_file_id

    now = datetime.now(timezone.utc)
    return RecoveryRun(
        run_id=run_id,
        case_id=case_id,
        filename=filename,
        format=format,
        status=status,
        started_at=now,
        completed_at=now,
        total_input_bytes=verified_bytes + reconstructed_bytes + missing_bytes,
        total_verified_bytes=verified_bytes,
        total_reconstructed_bytes=reconstructed_bytes,
        total_missing_bytes=missing_bytes,
        confidence={"total": confidence_score},
        provenance=prov,
    )


def test_18_cluster_interpretation_get_missing_case_returns_404(client: TestClient):
    """TEST 18: GET cluster interpretation with non-existent case returns 404."""
    res = client.get("/api/cases/non_existent_case_18/clusters/cluster_01/interpretation")
    assert res.status_code == 404
    assert "Case 'non_existent_case_18' not found" in res.json()["detail"]


def test_19_cluster_interpretation_get_missing_cluster_returns_404(client: TestClient):
    """TEST 19: GET cluster interpretation with valid case but non-existent cluster returns 404."""
    from backend.app.store import store
    case = store.create_case("M353.4 Test 19 Case")
    run = _make_test_recovery_run("run_test_19", case.case_id, evidence_start=0, evidence_end=100)
    store.add_recovery_run(run)

    res = client.get(f"/api/cases/{case.case_id}/clusters/non_existent_cluster_19/interpretation")
    assert res.status_code == 404
    assert f"Cluster 'non_existent_cluster_19' not found in case '{case.case_id}'" in res.json()["detail"]


def test_20_cluster_interpretation_get_uninterpreted_returns_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """TEST 20: GET cluster with no interpretation returns 404.

    Verifies:
    - Status is 404 with guidance message.
    - Zero provider invocations.
    - Zero cache mutations.
    - Zero SQLite writes.
    """
    from backend.app.store import store
    from backend.app.recovery.graph import build_case_evidence_graph
    from backend.app.scoring.interpretation_service import (
        get_interpretation_service,
        compute_cluster_fingerprint,
        InterpretationService,
    )

    def forbid_provider(*args, **kwargs):
        raise AssertionError("Provider must NOT be invoked during GET")

    monkeypatch.setattr(InterpretationService, "_invoke_cluster_with_fallback", forbid_provider)

    case = store.create_case("M353.4 Test 20 Case")
    run = _make_test_recovery_run("run_test_20", case.case_id, evidence_start=0, evidence_end=200)
    store.add_recovery_run(run)

    graph = build_case_evidence_graph(case.case_id, store=store)
    assert len(graph.clusters) > 0
    cluster = graph.clusters[0]

    service = get_interpretation_service(store)
    cluster_fp = compute_cluster_fingerprint(cluster, graph)
    cache_key = (case.case_id, cluster.cluster_id, cluster_fp)
    # Ensure cache is clear for this cluster
    service._cluster_cache.pop(cache_key, None)
    initial_cache_len = len(service._cluster_cache)

    res = client.get(f"/api/cases/{case.case_id}/clusters/{cluster.cluster_id}/interpretation")
    assert res.status_code == 404
    assert res.json()["detail"] == f"Interpretation not generated for cluster '{cluster.cluster_id}'. Call POST to generate."

    # Cache length must remain unchanged
    assert len(service._cluster_cache) == initial_cache_len
    assert cache_key not in service._cluster_cache


def test_21_cluster_interpretation_get_cached_returns_200(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """TEST 21: GET cluster with valid cached interpretation returns 200 with cached=True.

    Verifies:
    - Status 200.
    - Returns valid GroundedClusterInterpretation.
    - cached is True.
    - Zero provider invocations.
    - Zero regeneration.
    """
    from backend.app.store import store
    from backend.app.recovery.graph import build_case_evidence_graph
    from backend.app.scoring.interpretation_service import (
        get_interpretation_service,
        compute_cluster_fingerprint,
        InterpretationService,
    )
    from backend.app.models.interpretation import (
        GroundedClusterInterpretation,
        ProviderInterpretationOutput,
    )

    case = store.create_case("M353.4 Test 21 Case")
    run = _make_test_recovery_run("run_test_21", case.case_id, evidence_start=0, evidence_end=300)
    store.add_recovery_run(run)

    graph = build_case_evidence_graph(case.case_id, store=store)
    assert len(graph.clusters) > 0
    cluster = graph.clusters[0]

    service = get_interpretation_service(store)
    cluster_fp = compute_cluster_fingerprint(cluster, graph)
    cache_key = (case.case_id, cluster.cluster_id, cluster_fp)

    # Seed the cache directly
    facts = service.extract_cluster_facts(cluster, graph, case_id=case.case_id)
    seeded_interp = GroundedClusterInterpretation(
        facts=facts,
        relationships=[],
        interpretation=ProviderInterpretationOutput(
            summary="Seeded cluster interpretation summary",
            details=["Seeded observation 1"],
            assessment="Seeded cluster assessment",
            structural_context="Seeded structural context",
            limitations="No limitations detected",
            recommended_next_steps="Review cluster bounds",
        ),
        source="DETERMINISTIC_RULES",
        cached=False,
        generated_at="2026-10-02T12:00:00Z",
        cluster_fingerprint=cluster_fp,
    )
    service._put_cluster_cache(cache_key, seeded_interp)

    def forbid_provider(*args, **kwargs):
        raise AssertionError("Provider must NOT be invoked when cache hit on GET")

    monkeypatch.setattr(InterpretationService, "_invoke_cluster_with_fallback", forbid_provider)

    res = client.get(f"/api/cases/{case.case_id}/clusters/{cluster.cluster_id}/interpretation")
    assert res.status_code == 200
    data = res.json()

    validated = GroundedClusterInterpretation.model_validate(data)
    assert validated.cached is True
    assert validated.facts.cluster_id == cluster.cluster_id
    assert validated.interpretation.summary == "Seeded cluster interpretation summary"
    assert validated.cluster_fingerprint == cluster_fp


def test_22_cluster_interpretation_post_generates(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """TEST 22: POST cluster interpretation without existing cache generates fresh interpretation.

    Verifies:
    - Status 200.
    - GroundedClusterInterpretation returned with cached=False.
    - Grounded facts correspond to deterministic cluster facts.
    - Cached in service._cluster_cache.
    """
    from backend.app.store import store
    from backend.app.recovery.graph import build_case_evidence_graph
    from backend.app.scoring.interpretation_service import (
        get_interpretation_service,
        compute_cluster_fingerprint,
    )
    from backend.app.models.interpretation import GroundedClusterInterpretation

    monkeypatch.setenv("RECOVERIX_OFFLINE", "1")

    case = store.create_case("M353.4 Test 22 Case")
    run = _make_test_recovery_run("run_test_22", case.case_id, evidence_start=100, evidence_end=400, format="png")
    store.add_recovery_run(run)

    graph = build_case_evidence_graph(case.case_id, store=store)
    cluster = graph.clusters[0]

    service = get_interpretation_service(store)
    cluster_fp = compute_cluster_fingerprint(cluster, graph)
    cache_key = (case.case_id, cluster.cluster_id, cluster_fp)
    service._cluster_cache.pop(cache_key, None)

    res = client.post(f"/api/cases/{case.case_id}/clusters/{cluster.cluster_id}/interpretation")
    assert res.status_code == 200
    data = res.json()

    validated = GroundedClusterInterpretation.model_validate(data)
    assert validated.cached is False
    assert validated.facts.cluster_id == cluster.cluster_id
    assert validated.facts.cluster_start == 100
    assert validated.facts.cluster_end == 400
    assert validated.cluster_fingerprint == cluster_fp
    assert validated.source == "DETERMINISTIC_RULES"

    # Must be stored in cache
    assert cache_key in service._cluster_cache


def test_23_cluster_interpretation_post_reuses_cache(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """TEST 23: POST with force_refresh=False reuses existing cache without calling provider.

    Verifies:
    - Default force_refresh=False reuses existing cache entry.
    - Explicit force_refresh=false query param reuses existing cache entry.
    - Provider is not invoked.
    - cached is True in response.
    """
    from backend.app.store import store
    from backend.app.recovery.graph import build_case_evidence_graph
    from backend.app.scoring.interpretation_service import (
        get_interpretation_service,
        compute_cluster_fingerprint,
        InterpretationService,
    )
    from backend.app.models.interpretation import (
        GroundedClusterInterpretation,
        ProviderInterpretationOutput,
    )

    case = store.create_case("M353.4 Test 23 Case")
    run = _make_test_recovery_run("run_test_23", case.case_id, evidence_start=0, evidence_end=250)
    store.add_recovery_run(run)

    graph = build_case_evidence_graph(case.case_id, store=store)
    cluster = graph.clusters[0]

    service = get_interpretation_service(store)
    cluster_fp = compute_cluster_fingerprint(cluster, graph)
    cache_key = (case.case_id, cluster.cluster_id, cluster_fp)

    facts = service.extract_cluster_facts(cluster, graph, case_id=case.case_id)
    seeded_interp = GroundedClusterInterpretation(
        facts=facts,
        relationships=[],
        interpretation=ProviderInterpretationOutput(
            summary="Existing cluster summary to be reused",
            details=["Detail 1"],
            assessment="Assessment 1",
            structural_context="Context 1",
            limitations="No limitations",
            recommended_next_steps="Next step 1",
        ),
        source="DETERMINISTIC_RULES",
        cached=False,
        generated_at="2026-10-02T12:00:00Z",
        cluster_fingerprint=cluster_fp,
    )
    service._put_cluster_cache(cache_key, seeded_interp)

    def forbid_provider(*args, **kwargs):
        raise AssertionError("Provider must NOT be invoked when cache hit on POST with force_refresh=False")

    monkeypatch.setattr(InterpretationService, "_invoke_cluster_with_fallback", forbid_provider)

    # 1. Default POST (force_refresh omitted)
    res_def = client.post(f"/api/cases/{case.case_id}/clusters/{cluster.cluster_id}/interpretation")
    assert res_def.status_code == 200
    data_def = res_def.json()
    assert data_def["cached"] is True
    assert data_def["interpretation"]["summary"] == "Existing cluster summary to be reused"

    # 2. Explicit POST with force_refresh=false
    res_param = client.post(f"/api/cases/{case.case_id}/clusters/{cluster.cluster_id}/interpretation?force_refresh=false")
    assert res_param.status_code == 200
    data_param = res_param.json()
    assert data_param["cached"] is True
    assert data_param["interpretation"]["summary"] == "Existing cluster summary to be reused"


def test_24_cluster_interpretation_post_force_refresh(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """TEST 24: POST with force_refresh=True regenerates and replaces cache entry.

    Verifies:
    - Provider is invoked.
    - Response has cached=False and newly generated content.
    - Cache is updated with newly generated interpretation.
    """
    from backend.app.store import store
    from backend.app.recovery.graph import build_case_evidence_graph
    from backend.app.scoring.interpretation_service import (
        get_interpretation_service,
        compute_cluster_fingerprint,
        InterpretationService,
    )
    from backend.app.models.interpretation import (
        GroundedClusterInterpretation,
        ProviderInterpretationOutput,
    )

    case = store.create_case("M353.4 Test 24 Case")
    run = _make_test_recovery_run("run_test_24", case.case_id, evidence_start=0, evidence_end=250)
    store.add_recovery_run(run)

    graph = build_case_evidence_graph(case.case_id, store=store)
    cluster = graph.clusters[0]

    service = get_interpretation_service(store)
    cluster_fp = compute_cluster_fingerprint(cluster, graph)
    cache_key = (case.case_id, cluster.cluster_id, cluster_fp)

    facts = service.extract_cluster_facts(cluster, graph, case_id=case.case_id)
    old_interp = GroundedClusterInterpretation(
        facts=facts,
        relationships=[],
        interpretation=ProviderInterpretationOutput(
            summary="Outdated cluster summary",
            details=["Old detail"],
            assessment="Old assessment",
            structural_context="Old context",
            limitations="Old limitations",
            recommended_next_steps="Old next steps",
        ),
        source="DETERMINISTIC_RULES",
        cached=False,
        generated_at="2026-10-01T00:00:00Z",
        cluster_fingerprint=cluster_fp,
    )
    service._put_cluster_cache(cache_key, old_interp)

    def mock_invoke(self, context):
        return ProviderInterpretationOutput(
            summary="Freshly regenerated cluster interpretation summary",
            details=["Fresh detail 1"],
            assessment="Fresh assessment",
            structural_context="Fresh context",
            limitations="Fresh limitations",
            recommended_next_steps="Fresh next steps",
        ), "GEMINI_1_5_FLASH"

    monkeypatch.setattr(InterpretationService, "_invoke_cluster_with_fallback", mock_invoke)

    res = client.post(f"/api/cases/{case.case_id}/clusters/{cluster.cluster_id}/interpretation?force_refresh=true")
    assert res.status_code == 200
    data = res.json()

    assert data["cached"] is False
    assert data["source"] == "GEMINI_1_5_FLASH"
    assert data["interpretation"]["summary"] == "Freshly regenerated cluster interpretation summary"

    # Cached value must be updated
    cached_val = service._cluster_cache[cache_key]
    assert cached_val.interpretation.summary == "Freshly regenerated cluster interpretation summary"
    assert cached_val.source == "GEMINI_1_5_FLASH"


def test_25_unknown_scope_cluster_semantics(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """TEST 25: Unknown-scope nodes remain isolated singleton clusters and are correctly interpreted.

    Verifies:
    - Nodes without evidence_file_id do not merge with other scoped or unscoped nodes.
    - Each remains an isolated singleton cluster (Rule 3.4).
    - API endpoint routes and interprets the unknown-scope cluster correctly.
    """
    from backend.app.store import store
    from backend.app.recovery.graph import build_case_evidence_graph
    from backend.app.models.interpretation import GroundedClusterInterpretation

    monkeypatch.setenv("RECOVERIX_OFFLINE", "1")

    case = store.create_case("M353.4 Test 25 Case")
    # Create two runs with evidence_file_id=None (unknown scope)
    run_unscoped_1 = _make_test_recovery_run(
        "run_unscoped_01", case.case_id, evidence_start=100, evidence_end=200, evidence_file_id=None
    )
    run_unscoped_2 = _make_test_recovery_run(
        "run_unscoped_02", case.case_id, evidence_start=150, evidence_end=250, evidence_file_id=None
    )
    store.add_recovery_run(run_unscoped_1)
    store.add_recovery_run(run_unscoped_2)

    graph = build_case_evidence_graph(case.case_id, store=store)
    # Under Rule 3.4, unknown-scope nodes are NOT merged into a shared cluster even if they overlap!
    # They MUST each be their own singleton cluster.
    unscoped_clusters = [c for c in graph.clusters if c.evidence_file_id is None]
    assert len(unscoped_clusters) == 2
    for c in unscoped_clusters:
        assert c.total_nodes == 1
        assert c.relationship_classification == "ISOLATED"

    target_cluster = unscoped_clusters[0]

    # Generate interpretation via API
    res = client.post(f"/api/cases/{case.case_id}/clusters/{target_cluster.cluster_id}/interpretation")
    assert res.status_code == 200
    data = res.json()

    interp = GroundedClusterInterpretation.model_validate(data)
    assert interp.facts.cluster_id == target_cluster.cluster_id
    assert interp.facts.evidence_file_id is None
    assert interp.facts.relationship_classification == "ISOLATED"
    assert interp.facts.total_nodes == 1


def test_26_cluster_fingerprint_changes_invalidates_cache_identity(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """TEST 26: Changing cluster structure changes fingerprint and prevents stale cache reads.

    Verifies:
    - Interpreting cluster v1 caches under fingerprint 1.
    - Modifying member node facts changes cluster fingerprint.
    - GET with new fingerprint returns 404 (not yet generated for new fingerprint).
    - POST with new fingerprint generates and caches under new fingerprint.
    """
    from backend.app.store import store
    from backend.app.recovery.graph import build_case_evidence_graph
    from backend.app.scoring.interpretation_service import (
        get_interpretation_service,
        compute_cluster_fingerprint,
    )

    monkeypatch.setenv("RECOVERIX_OFFLINE", "1")

    case = store.create_case("M353.4 Test 26 Case")
    run_v1 = _make_test_recovery_run("run_fp_test", case.case_id, evidence_start=0, evidence_end=500, verified_bytes=500)
    store.add_recovery_run(run_v1)

    graph_v1 = build_case_evidence_graph(case.case_id, store=store)
    cluster_v1 = graph_v1.clusters[0]
    fp_v1 = compute_cluster_fingerprint(cluster_v1, graph_v1)

    # Generate interpretation for v1
    res_post_v1 = client.post(f"/api/cases/{case.case_id}/clusters/{cluster_v1.cluster_id}/interpretation")
    assert res_post_v1.status_code == 200
    assert res_post_v1.json()["cluster_fingerprint"] == fp_v1

    # Verify GET returns 200 for v1
    res_get_v1 = client.get(f"/api/cases/{case.case_id}/clusters/{cluster_v1.cluster_id}/interpretation")
    assert res_get_v1.status_code == 200
    assert res_get_v1.json()["cached"] is True

    # Now modify the run (e.g. verified_bytes from 500 to 400, reconstructed_bytes to 100)
    run_v2 = _make_test_recovery_run(
        "run_fp_test", case.case_id, evidence_start=0, evidence_end=500, verified_bytes=400, reconstructed_bytes=100
    )
    store.add_recovery_run(run_v2)

    graph_v2 = build_case_evidence_graph(case.case_id, store=store)
    cluster_v2 = graph_v2.clusters[0]
    fp_v2 = compute_cluster_fingerprint(cluster_v2, graph_v2)
    assert fp_v1 != fp_v2, "Cluster fingerprint must change when member bytes change"

    # GET must now return 404 because cache has no entry for (case_id, cluster_id, fp_v2)
    res_get_v2 = client.get(f"/api/cases/{case.case_id}/clusters/{cluster_v2.cluster_id}/interpretation")
    assert res_get_v2.status_code == 404
    assert "Call POST to generate" in res_get_v2.json()["detail"]

    # POST generates under new fingerprint
    res_post_v2 = client.post(f"/api/cases/{case.case_id}/clusters/{cluster_v2.cluster_id}/interpretation")
    assert res_post_v2.status_code == 200
    assert res_post_v2.json()["cluster_fingerprint"] == fp_v2
    assert res_post_v2.json()["cached"] is False


def test_27_malformed_cached_cluster_interpretation_returns_controlled_500(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """TEST 27: Malformed cached cluster interpretation returns controlled 500.

    Verifies:
    - Status is 500.
    - Error detail explains cached interpretation is malformed or invalid.
    - Zero provider invocations.
    - GET does not regenerate or overwrite.
    """
    from backend.app.store import store
    from backend.app.recovery.graph import build_case_evidence_graph
    from backend.app.scoring.interpretation_service import (
        get_interpretation_service,
        compute_cluster_fingerprint,
        InterpretationService,
    )

    case = store.create_case("M353.4 Test 27 Case")
    run = _make_test_recovery_run("run_test_27", case.case_id, evidence_start=0, evidence_end=150)
    store.add_recovery_run(run)

    graph = build_case_evidence_graph(case.case_id, store=store)
    cluster = graph.clusters[0]

    service = get_interpretation_service(store)
    cluster_fp = compute_cluster_fingerprint(cluster, graph)
    cache_key = (case.case_id, cluster.cluster_id, cluster_fp)

    # Inject malformed data into cache
    service._cluster_cache[cache_key] = "NOT_A_VALID_INTERPRETATION_JSON{{{"

    def forbid_provider(*args, **kwargs):
        raise AssertionError("Provider must NOT be invoked when reading malformed cache on GET")

    monkeypatch.setattr(InterpretationService, "_invoke_cluster_with_fallback", forbid_provider)

    res = client.get(f"/api/cases/{case.case_id}/clusters/{cluster.cluster_id}/interpretation")
    assert res.status_code == 500
    assert res.json()["detail"] == f"Cached interpretation for cluster '{cluster.cluster_id}' is malformed or invalid"

    # Inject schema-violating dict
    service._cluster_cache[cache_key] = {"unexpected_key": 999}
    res_dict = client.get(f"/api/cases/{case.case_id}/clusters/{cluster.cluster_id}/interpretation")
    assert res_dict.status_code == 500
    assert res_dict.json()["detail"] == f"Cached interpretation for cluster '{cluster.cluster_id}' is malformed or invalid"
