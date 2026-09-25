"""
test_llm_explainer.py — Comprehensive tests for Grounded LLM Evidence Explanation layer.

Covers all Phase 8 test requirements:
1. LLM disabled (LLM_ENABLED=false) -> deterministic fallback.
2. No API key (LLM_API_KEY="") -> deterministic fallback.
3. LLM success -> validated LLM explanation returned.
4. LLM timeout/error -> deterministic fallback.
5. Malformed LLM response -> deterministic fallback.
6. Cache prevents repeated LLM calls on /artifacts/{id}/explain.
7. Deterministic forensic fields remain unchanged.
8. reconstructed_bytes > 0 remains PARTIALLY_RECOVERED regardless of LLM.
9. LLM cannot alter confidence/status/provenance.
10. /explain endpoint returns valid schema (summary + details).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
import httpx
from fastapi.testclient import TestClient

# Ensure imports work from the project root.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.app.main import app
from backend.app.store import store
from backend.app.scoring.explainer import generate_explanation, call_llm_explanation, build_deterministic_explanation

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_store_and_env(monkeypatch):
    """Reset the in-memory store and environment variables before each test."""
    store.clear()
    monkeypatch.delenv("LLM_ENABLED", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    yield
    store.clear()


# Sample deterministic artifact facts for testing
SAMPLE_FACTS = {
    "artifact_id": "art_test001",
    "fmt": "csv",
    "category": "DATABASE_LOG",
    "priority": "HIGH",
    "status": "PARTIALLY_RECOVERED",
    "confidence_score": 78,
    "score_breakdown": {
        "header_validity": 20,
        "footer_validity": 0,
        "structural_validation": 28,
        "size_plausibility": 15,
        "reconstruction_integrity": 15,
    },
    "provenance": {
        "verified_bytes": 8400,
        "reconstructed_bytes": 1200,
        "missing_bytes": 400,
        "reconstruction_method": "BIFRAGMENT_GAP",
        "validation_status": "PASSED",
    },
    "content_preview": "id,amount,date,status\n1,500.00,2026-09-21,COMPLETED\n",
}


# ── 1. LLM Disabled -> Deterministic Fallback ──────────────────────────────

def test_llm_disabled_returns_fallback(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "false")
    monkeypatch.setenv("LLM_API_KEY", "test_key_123")

    with patch("backend.app.scoring.explainer.call_llm_explanation") as mock_call:
        res = generate_explanation(**SAMPLE_FACTS)
        assert mock_call.call_count == 0
        assert res["summary"].startswith("Database Log artifact (CSV)")
        assert "Status: PARTIALLY_RECOVERED (Confidence Score: 78/100)" in res["details"]


# ── 2. No API Key -> Deterministic Fallback ───────────────────────────────

def test_no_api_key_returns_fallback(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "")

    res = generate_explanation(**SAMPLE_FACTS)
    assert res == build_deterministic_explanation(**SAMPLE_FACTS)


# ── 3. LLM Success -> Validated LLM Explanation ───────────────────────────

def test_llm_success_returns_validated_explanation(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "valid_secret_key")

    mock_response_json = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "summary": "AI Summary: Financial ledger database log partially recovered across fragmented gap.",
                        "details": [
                            "8400 verified bytes recovered.",
                            "1200 bytes gap reconstructed via bounded bifragment algorithm.",
                            "HIGH priority assigned due to transaction indicators."
                        ]
                    })
                }
            }
        ]
    }

    mock_client = MagicMock()
    mock_post_res = MagicMock()
    mock_post_res.status_code = 200
    mock_post_res.json.return_value = mock_response_json
    mock_client.post.return_value = mock_post_res

    with patch("httpx.Client") as mock_httpx_class:
        mock_httpx_class.return_value.__enter__.return_value = mock_client
        res = generate_explanation(**SAMPLE_FACTS)

        assert res["summary"] == "AI Summary: Financial ledger database log partially recovered across fragmented gap."
        assert len(res["details"]) == 3
        assert "8400 verified bytes recovered." in res["details"]


# ── 4. LLM Timeout / HTTP Error -> Deterministic Fallback ────────────────

def test_llm_timeout_or_http_error_returns_fallback(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "valid_secret_key")

    mock_client = MagicMock()
    mock_client.post.side_effect = httpx.TimeoutException("Connection timed out")

    with patch("httpx.Client") as mock_httpx_class:
        mock_httpx_class.return_value.__enter__.return_value = mock_client
        res = generate_explanation(**SAMPLE_FACTS)

        # Must fall back gracefully to deterministic explanation
        assert res == build_deterministic_explanation(**SAMPLE_FACTS)


# ── 5. Malformed LLM Response -> Deterministic Fallback ───────────────────

def test_malformed_llm_response_returns_fallback(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "valid_secret_key")

    # Test cases of invalid JSON structure from LLM
    invalid_payloads = [
        {"choices": [{"message": {"content": "Not JSON text"}}]},
        {"choices": [{"message": {"content": json.dumps({"summary": "no details list"})}}]},
        {"choices": [{"message": {"content": json.dumps({"details": ["no summary"]})}}]},
        {"choices": [{"message": {"content": json.dumps({"summary": "", "details": ["details"]})}}]},
        {"choices": [{"message": {"content": json.dumps({"summary": "sum", "details": []})}}]},
    ]

    for bad_payload in invalid_payloads:
        mock_client = MagicMock()
        mock_post_res = MagicMock()
        mock_post_res.status_code = 200
        mock_post_res.json.return_value = bad_payload
        mock_client.post.return_value = mock_post_res

        with patch("httpx.Client") as mock_httpx_class:
            mock_httpx_class.return_value.__enter__.return_value = mock_client
            res = generate_explanation(**SAMPLE_FACTS)
            assert res == build_deterministic_explanation(**SAMPLE_FACTS)


# ── 6. Cache Prevents Repeated LLM Calls ──────────────────────────────────

def test_cache_prevents_repeated_llm_calls(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "valid_secret_key")

    # Create a case and evidence in store
    create_res = client.post("/api/cases", json={"name": "Cache Test Case"})
    case_id = create_res.json()["case_id"]

    evidence_content = b"[SYNTHETIC_ARTIFACT_START]\nfilename: test.txt\ncontent\n[SYNTHETIC_ARTIFACT_END]"
    client.post(f"/api/cases/{case_id}/evidence", files={"file": ("test.txt", evidence_content, "text/plain")})

    mock_response_json = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "summary": "LLM Generated Brief",
                        "details": ["Detail point 1", "Detail point 2"]
                    })
                }
            }
        ]
    }

    mock_client = MagicMock()
    mock_post_res = MagicMock()
    mock_post_res.status_code = 200
    mock_post_res.json.return_value = mock_response_json
    mock_client.post.return_value = mock_post_res

    with patch("httpx.Client") as mock_httpx_class:
        mock_httpx_class.return_value.__enter__.return_value = mock_client

        # 1. Analyze case (first time LLM call happens)
        analyze_res = client.post(f"/api/cases/{case_id}/analyze")
        assert analyze_res.status_code == 200
        artifact_id = analyze_res.json()["artifacts"][0]["artifact_id"]

        call_count_after_analyze = mock_client.post.call_count

        # 2. Call /explain endpoint first time (should hit cache created during analyze)
        explain_res_1 = client.post(f"/api/artifacts/{artifact_id}/explain")
        assert explain_res_1.status_code == 200
        assert explain_res_1.json()["summary"] == "LLM Generated Brief"
        assert mock_client.post.call_count == call_count_after_analyze

        # 3. Call /explain endpoint second time (must hit cache, ZERO new HTTP requests)
        explain_res_2 = client.post(f"/api/artifacts/{artifact_id}/explain")
        assert explain_res_2.status_code == 200
        assert explain_res_2.json()["summary"] == "LLM Generated Brief"
        assert mock_client.post.call_count == call_count_after_analyze


# ── 7. Safety Invariant: Deterministic Forensic Fields Unchanged ─────────

def test_safety_invariant_forensic_fields_unchanged(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "valid_secret_key")

    create_res = client.post("/api/cases", json={"name": "Safety Test Case"})
    case_id = create_res.json()["case_id"]

    evidence_content = b"[SYNTHETIC_ARTIFACT_START]\nfilename: safety.txt\ncontent\n[SYNTHETIC_ARTIFACT_END]"
    client.post(f"/api/cases/{case_id}/evidence", files={"file": ("safety.txt", evidence_content, "text/plain")})

    mock_client = MagicMock()
    mock_post_res = MagicMock()
    mock_post_res.status_code = 200
    mock_post_res.json.return_value = {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "summary": "Hallucinated summary attempting to claim full recovery",
                    "details": ["Attempting to override status to FULLY_RECOVERED"]
                })
            }
        }]
    }
    mock_client.post.return_value = mock_post_res

    with patch("httpx.Client") as mock_httpx_class:
        mock_httpx_class.return_value.__enter__.return_value = mock_client

        analyze_res = client.post(f"/api/cases/{case_id}/analyze")
        art = analyze_res.json()["artifacts"][0]

        # Verify underlying deterministic forensic fields are strictly untouched
        assert art["confidence_score"] == 100
        assert art["status"] == "FULLY_RECOVERED"
        assert art["provenance"]["verified_bytes"] > 0
        assert art["provenance"]["reconstruction_method"] == "NONE"
        assert art["category"] == "DOCUMENT"
        assert art["priority"] == "LOW"


# ── 8. Mandatory Override Rule Preserved ──────────────────────────────────

def test_reconstructed_bytes_status_override_preserved():
    from backend.app.scoring.confidence import classify_recovery_status
    from backend.app.models.confidence import RecoveryStatus

    # Proving reconstructed_bytes > 0 forces PARTIALLY_RECOVERED even if score is 100
    status = classify_recovery_status(score=100, reconstructed_bytes=50, missing_bytes=50)
    assert status == RecoveryStatus.PARTIALLY_RECOVERED
    assert status.value == "PARTIALLY_RECOVERED"


# ── 9. LLM Cannot Alter Confidence/Status/Provenance ────────────────────

def test_llm_cannot_alter_confidence_status_provenance(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "valid_secret_key")

    create_res = client.post("/api/cases", json={"name": "Tamper Test Case"})
    case_id = create_res.json()["case_id"]

    evidence_content = b"[SYNTHETIC_ARTIFACT_START]\nheader_csv,val\n1,2\n[SYNTHETIC_ARTIFACT_END]"
    client.post(f"/api/cases/{case_id}/evidence", files={"file": ("tamper.csv", evidence_content, "text/csv")})

    analyze_res = client.post(f"/api/cases/{case_id}/analyze")
    artifact_id = analyze_res.json()["artifacts"][0]["artifact_id"]

    # Retrieve before explain
    art_before = client.get(f"/api/artifacts/{artifact_id}").json()

    # Request /explain
    explain_res = client.post(f"/api/artifacts/{artifact_id}/explain")
    assert explain_res.status_code == 200

    # Retrieve after explain
    art_after = client.get(f"/api/artifacts/{artifact_id}").json()

    # Assert deterministic fields are identical before and after
    assert art_before["confidence_score"] == art_after["confidence_score"]
    assert art_before["status"] == art_after["status"]
    assert art_before["provenance"] == art_after["provenance"]
    assert art_before["score_breakdown"] == art_after["score_breakdown"]


# ── 10. /explain Endpoint Returns Valid Schema ───────────────────────────

def test_explain_endpoint_schema_compliance():
    create_res = client.post("/api/cases", json={"name": "Schema Check Case"})
    case_id = create_res.json()["case_id"]

    evidence_content = b"[SYNTHETIC_ARTIFACT_START]\nschema check\n[SYNTHETIC_ARTIFACT_END]"
    client.post(f"/api/cases/{case_id}/evidence", files={"file": ("check.txt", evidence_content, "text/plain")})
    analyze_res = client.post(f"/api/cases/{case_id}/analyze")
    artifact_id = analyze_res.json()["artifacts"][0]["artifact_id"]

    res = client.post(f"/api/artifacts/{artifact_id}/explain")
    assert res.status_code == 200
    data = res.json()

    assert "summary" in data
    assert isinstance(data["summary"], str)
    assert len(data["summary"]) > 0

    assert "details" in data
    assert isinstance(data["details"], list)
    assert len(data["details"]) > 0
    assert all(isinstance(item, str) for item in data["details"])


# ── 11. Local Offline LLM Configuration & Target Endpoint Test ────────────

def test_local_llm_configuration_and_endpoint(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:8080/v1")
    monkeypatch.setenv("LLM_MODEL", "llama-3.2-3b-instruct")
    monkeypatch.setenv("LLM_API_KEY", "local")

    mock_response_json = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "summary": "Local llama.cpp summary: database log recovered.",
                        "details": ["Verified 8400 bytes.", "Local offline LLM active."]
                    })
                }
            }
        ]
    }

    mock_client = MagicMock()
    mock_post_res = MagicMock()
    mock_post_res.status_code = 200
    mock_post_res.json.return_value = mock_response_json
    mock_client.post.return_value = mock_post_res

    with patch("httpx.Client") as mock_httpx_class:
        mock_httpx_class.return_value.__enter__.return_value = mock_client
        res = generate_explanation(**SAMPLE_FACTS)

        # Verify correct target endpoint and payload passed to local server
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "http://127.0.0.1:8080/v1/chat/completions"
        assert call_args[1]["json"]["model"] == "llama-3.2-3b-instruct"
        assert res["summary"] == "Local llama.cpp summary: database log recovered."

