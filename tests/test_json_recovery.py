"""
test_json_recovery.py — Test suite for deterministic JSON Recovery.

Covers the required recovery cases:
  A. Intact JSON: full recovery, byte-exact, no reconstruction.
  B. Truncated but deterministically closable JSON: structural repair, R > 0,
     status is never FULLY_RECOVERED.
  C. Unknown missing content: no invented property/value, explicit M accounting,
     ambiguity preserved.
  D. Malformed / non-JSON evidence: safe rejection, never reinterpreted.
  E. Accounting identity: V + R + M == artifact budget; V + M == evidence size.
  F. No-FULLY rule: FULLY_RECOVERED only when R == 0 and M == 0.
  G. API surface: status, byte accounting, method, download, and safety.
  H. Detection: a .json artifact is never relabelled CSV/TXT.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.store import store
from backend.app.recovery.reconstructors.json import reconstruct_json
from backend.app.recovery.reconstruction import reconstruct_artifact
from backend.app.recovery.tracer import execute_traced_recovery

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_store():
    store.clear()
    yield
    store.clear()


# Canonical fixture (valid, moderately nested JSON).
FULL_JSON = (
    b'{"case":"recoverix","id":42,"tags":["a","b"],'
    b'"nested":{"k":"v","list":[1,2,3]}}'
)


def _acct(result):
    return result.verified_bytes + result.reconstructed_bytes + result.missing_bytes


# ── Case A: Intact JSON ─────────────────────────────────────────────

def test_a_intact_json_is_byte_exact_and_full():
    r = reconstruct_json(FULL_JSON)
    assert r.status == "FULLY_RECOVERED"
    assert r.success is True
    assert r.recovered_bytes == FULL_JSON
    assert r.verified_bytes == len(FULL_JSON)
    assert r.reconstructed_bytes == 0
    assert r.missing_bytes == 0
    # No ground truth was supplied, so the exact-match diagnostic stays unset:
    # the reconstruction never consulted an expected output.
    assert r.is_exact_match is None
    assert r.details["reconstruction_method"] == "JSON_STRUCTURAL_VALIDATION"
    # Output parses as JSON.
    json.loads(r.recovered_bytes)


def test_a_intact_json_via_dispatch():
    r = reconstruct_artifact("json", FULL_JSON)
    assert r.status == "FULLY_RECOVERED"
    assert r.recovered_bytes == FULL_JSON


# ── Case B: Deterministically closable truncation ───────────────────

def test_b_closable_prefix_appends_only_forced_closers():
    evidence = b'{"a":1,"b":[1,2,3'
    r = reconstruct_json(evidence)
    assert r.status == "PARTIALLY_RECOVERED"
    # The added bytes are exactly the forced closing sequence, nothing more.
    assert r.recovered_bytes == evidence + b"]}"
    assert r.details["appended_closers"] == "]}"
    assert r.reconstructed_bytes == len(b"]}")
    assert r.verified_bytes == len(evidence)
    assert r.missing_bytes == 0
    # The reconstruction yields valid JSON.
    assert json.loads(r.recovered_bytes) == {"a": 1, "b": [1, 2, 3]}
    # Structural reconstruction must not be reported as full recovery.
    assert r.status != "FULLY_RECOVERED"


def test_b_nested_closable_prefix():
    evidence = b'{"a":{"b":[1,2'
    r = reconstruct_json(evidence)
    assert r.status == "PARTIALLY_RECOVERED"
    # Stack is {,[,{ -> closers are emitted innermost-first: ]}}
    assert r.recovered_bytes == evidence + b"]}}"
    assert r.details["appended_closers"] == "]}}"
    assert r.reconstructed_bytes == 3
    json.loads(r.recovered_bytes)


def test_b_trailing_number_is_complete_not_truncated():
    # The trailing "12" is a whole value; the only deficiency is the closer.
    r = reconstruct_json(b'{"a":1.5,"b":12')
    assert r.status == "PARTIALLY_RECOVERED"
    assert r.details["reconstruction_method"] == "JSON_STRUCTURAL_CLOSURE"
    assert r.reconstructed_bytes == 1
    assert json.loads(r.recovered_bytes) == {"a": 1.5, "b": 12}


# ── Case C: Unknown missing content (never invented) ────────────────

@pytest.mark.parametrize(
    "evidence, reason_fragment",
    [
        (b'{"a":1,"b":', "value"),
        (b'{"a":1,', "object body"),
        (b'{"ok":true,"x":tru', "literal"),
    ],
)
def test_c_unknown_content_is_not_invented(evidence, reason_fragment):
    r = reconstruct_json(evidence)
    # Never FULLY: something is unresolved.
    assert r.status != "FULLY_RECOVERED"
    # Explicit missing accounting: the unresolved tail is reported, not guessed.
    assert r.missing_bytes > 0
    # The verified prefix is preserved as-is; no structural bytes invented.
    assert r.reconstructed_bytes == 0
    assert r.recovered_bytes == evidence[: len(evidence) - r.missing_bytes]
    # Refusal is explained.
    assert r.details["reconstruction_method"] == "JSON_UNRESOLVED_CONTENT"
    assert "notice" in r.details
    assert reason_fragment in r.details["prefix_reason"] or reason_fragment in r.details["refused"]


def test_c_open_brace_only_is_unrecoverable_not_invented():
    # "{" alone is consistent with "{}" and with '{"a":1}'; do not pick one.
    r = reconstruct_json(b"{")
    assert r.status == "UNRECOVERABLE"
    assert r.recovered_bytes == b""
    assert r.verified_bytes == 0
    assert r.reconstructed_bytes == 0
    assert r.missing_bytes == 1


# ── Case D: Malformed / non-JSON evidence ───────────────────────────

@pytest.mark.parametrize(
    "data",
    [
        b"this is not json at all!!",
        b"{invalid json here",
        b"\xff\xfe\x00binary\x00",
    ],
)
def test_d_malformed_json_rejected_safely(data):
    r = reconstruct_json(data)
    assert r.status == "UNRECOVERABLE"
    assert r.success is False
    assert r.recovered_bytes == b""
    assert r.reconstructed_bytes == 0
    # Every evidence byte is accounted as missing (or as invalid), never guessed.
    assert r.verified_bytes + r.missing_bytes == len(data)


def test_d_empty_evidence():
    r = reconstruct_json(b"")
    assert r.status == "UNRECOVERABLE"
    assert r.recovered_bytes == b""


# ── Case E: Accounting identity ─────────────────────────────────────

@pytest.mark.parametrize(
    "evidence",
    [
        FULL_JSON,
        b'{"a":1,"b":[1,2,3',
        b'{"a":{"b":[1,2',
        b'{"a":1,"b":',
        b'{"a":1,',
        b'{"ok":true,"x":tru',
        b"{",
        b"not json",
        b"",
    ],
)
def test_e_accounting_identities_hold(evidence):
    r = reconstruct_json(evidence)
    emitted = len(r.recovered_bytes)
    # Every emitted byte is either verified evidence or structural repair.
    assert r.verified_bytes + r.reconstructed_bytes == emitted
    # Every input byte is either emitted as verified evidence or dropped missing.
    assert r.verified_bytes + r.missing_bytes == len(evidence)
    # The three-way artifact budget.
    assert _acct(r) == emitted + r.missing_bytes


# ── Case F: FULLY_RECOVERED only when nothing reconstructed/missing ──

@pytest.mark.parametrize(
    "evidence",
    [
        FULL_JSON,
        b'{"a":1,"b":[1,2,3',
        b'{"a":{"b":[1,2',
        b'{"a":1,"b":',
        b'{"a":1,',
        b"{",
        b"not json",
    ],
)
def test_f_full_recovery_never_overclaims(evidence):
    r = reconstruct_json(evidence)
    if r.reconstructed_bytes > 0 or r.missing_bytes > 0:
        assert r.status != "FULLY_RECOVERED"


# ── Case G: Tracer / API surface ────────────────────────────────────

def test_g_tracer_closable_json_status_and_method():
    evidence = b'{"a":1,"b":[1,2,3'
    run = execute_traced_recovery(filename="evidence.json", content=evidence)
    assert run.format == "json"
    assert run.status == "PARTIALLY_RECOVERED"
    assert run.total_reconstructed_bytes == 2
    assert run.total_missing_bytes == 0
    # The artifact budget identity holds at the run level.
    assert run.total_input_bytes == (
        run.total_verified_bytes
        + run.total_reconstructed_bytes
        + run.total_missing_bytes
    )
    # The method explicitly identifies JSON structural reconstruction.
    assert "JSON" in run.provenance["reconstruction_method"]
    # Provenance records the actual uploaded evidence size.
    assert run.provenance["evidence_size"] == len(evidence)


def test_g_tracer_intact_json_is_full_and_exact():
    run = execute_traced_recovery(filename="evidence.json", content=FULL_JSON)
    assert run.format == "json"
    assert run.status == "FULLY_RECOVERED"
    assert run.total_verified_bytes == len(FULL_JSON)
    assert run.total_reconstructed_bytes == 0
    assert run.total_missing_bytes == 0
    assert run.total_input_bytes == len(FULL_JSON)


def test_g_tracer_malformed_json_is_unrecoverable():
    run = execute_traced_recovery(filename="evidence.json", content=b"not json at all")
    assert run.format == "json"
    assert run.status == "UNRECOVERABLE"
    assert run.total_verified_bytes == 0
    assert run.total_reconstructed_bytes == 0
    assert run.total_missing_bytes == len(b"not json at all")


def test_g_api_closable_json_reports_partial_and_downloadable():
    evidence = b'{"a":1,"b":[1,2,3'
    response = client.post(
        "/api/recover-file",
        files={"file": ("evidence.json", evidence, "application/json")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["format"] == "json"
    assert data["status"] == "PARTIALLY_RECOVERED"
    # Structural reconstruction present and honestly reported.
    assert data["reconstructed_bytes"] == 2
    assert data["missing_bytes"] == 0
    assert "JSON" in data["reconstruction_method"]
    # Not falsely full.
    assert data["status"] != "FULLY_RECOVERED"
    assert data["is_downloadable"] is True


def test_g_api_closable_json_download_is_valid():
    evidence = b'{"a":1,"b":[1,2,3'
    response = client.post(
        "/api/recover-file",
        files={"file": ("evidence.json", evidence, "application/json")},
    )
    download_url = response.json()["download_url"]
    dl = client.get(download_url)
    assert dl.status_code == 200
    downloaded = dl.content
    assert downloaded == evidence + b"]}"
    # The recovered download is genuinely valid JSON.
    assert json.loads(downloaded) == {"a": 1, "b": [1, 2, 3]}


def test_g_api_unknown_content_reports_missing_and_not_full():
    evidence = b'{"a":1,"b":'
    response = client.post(
        "/api/recover-file",
        files={"file": ("evidence.json", evidence, "application/json")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["format"] == "json"
    assert data["status"] != "FULLY_RECOVERED"
    assert data["missing_bytes"] > 0
    assert data["reconstructed_bytes"] == 0


# ── Case H: A .json artifact is never relabelled CSV/TXT ─────────────

@pytest.mark.parametrize(
    "evidence",
    [
        b'{"a":1,"b":[1,2,3',
        b'{"a":1,"b":',
        b"not json at all",
    ],
)
def test_h_json_is_never_reinterpreted_as_other_formats(evidence):
    run = execute_traced_recovery(filename="evidence.json", content=evidence)
    # The run stays JSON regardless of what other validators might accept.
    assert run.format == "json"
    # Pass-through mislabeling would show V=R=len(content); we never do that.
    assert not (
        run.total_verified_bytes == len(evidence)
        and run.total_reconstructed_bytes == len(evidence)
    )
