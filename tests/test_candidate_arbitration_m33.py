"""
test_candidate_arbitration_m33.py — Comprehensive test suite for Recoverix Milestone 3.3.3.

Tests:
  - Physical candidate coordinates (evidence_start, evidence_end, coordinate_system)
  - Whole buffer fallback coordinates (evidence_start=0, evidence_end=len(content))
  - Candidate deduplication by (offset, format) with deterministic priority
  - Spatial relationships (COEXTENSIVE, CONTAINS, CONTAINED_BY, OVERLAPS)
  - Invariant: both ends MUST be known to prove spatial relationships
  - Post-discovery candidate processing cap (MAX_CANDIDATES = 250)
  - Provenance and PipelineEvent propagation
  - Blind multi-format unsuppressed discovery across PNG, JPEG, PDF, JSON, XML, TXT, CSV
  - Bifragment pair physical coordinates and unchanged gap semantics
  - Isolated error recovery runs with coordinates and error reporting
  - SQLite persistence round-trip with Milestone 3.3.3 provenance
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
import pytest

from backend.app.models.recovery_run import RecoveryRun, PipelineEvent
from backend.app.recovery.scanner import (
    Candidate,
    CandidateRelationship,
    scan_evidence,
    get_last_scan_metadata,
    _dedup_candidates,
    _compute_candidate_relationships,
    MAX_CANDIDATES,
)
from backend.app.recovery.tracer import (
    execute_traced_recoveries,
    execute_traced_recovery,
)
from backend.app.recovery.signatures import (
    PNG_SIGNATURE,
    PDF_HEADER_SIGNATURE,
    PDF_TRAILER_SIGNATURE,
    JPEG_SOI,
    JPEG_EOI,
    XML_HEADER_SIGNATURE,
)
from backend.app.store import store


# ═════════════════════════════════════════════════════════════════════════════
# 1. PHYSICAL CANDIDATE COORDINATES TESTS
# ═════════════════════════════════════════════════════════════════════════════

def test_1_physical_coordinates_known_end():
    """1. Candidate with known end offset provides exact physical evidence coordinates."""
    cand = Candidate(
        candidate_id="cand-0",
        format="json",
        mime_type="application/json",
        category="structured",
        offset=128,
        detected_header_length=1,
        estimated_end_offset=384,
        detection_method="heuristic_json_container",
    )
    assert cand.evidence_start == 128
    assert cand.evidence_end == 384

    # Build dummy content and execute recovery
    content = b"X" * 128 + b'{"status": "ok", "value": 42}' + b" " * (384 - 128 - 29) + b"Y" * 100
    runs = execute_traced_recoveries("dump.raw", content, candidates=[cand], detection_mode="blind")
    assert len(runs) == 1
    run = runs[0]

    assert run.provenance["evidence_start"] == 128
    assert run.provenance["evidence_end"] == 384
    assert run.provenance["coordinate_system"] == "physical_evidence_offsets"
    assert run.provenance["detection_method"] == "heuristic_json_container"

    # Verify CANDIDATE_FOUND event contains coordinates
    found_events = [e for e in run.events if e.event_type == "CANDIDATE_FOUND"]
    assert len(found_events) >= 1
    info = found_events[0].relevant_artifact_info or {}
    assert info.get("evidence_start") == 128
    assert info.get("evidence_end") == 384
    assert info.get("coordinate_system") == "physical_evidence_offsets"


def test_2_physical_coordinates_unknown_end():
    """2. Candidate with unknown end has evidence_end=None and does not fabricate coordinates."""
    cand = Candidate(
        candidate_id="cand-0",
        format="png",
        mime_type="image/png",
        category="image",
        offset=64,
        detected_header_length=8,
        estimated_end_offset=None,
        detection_method="magic_bytes",
    )
    assert cand.evidence_start == 64
    assert cand.evidence_end is None

    content = b"\x00" * 64 + PNG_SIGNATURE + b"\x00" * 200
    runs = execute_traced_recoveries("evidence.raw", content, candidates=[cand], detection_mode="blind")
    assert len(runs) == 1
    run = runs[0]

    assert run.provenance["evidence_start"] == 64
    assert run.provenance["evidence_end"] is None
    assert run.provenance["coordinate_system"] == "physical_evidence_offsets"

    found_events = [e for e in run.events if e.event_type == "CANDIDATE_FOUND"]
    assert len(found_events) >= 1
    info = found_events[0].relevant_artifact_info or {}
    assert info.get("evidence_start") == 64
    assert info.get("evidence_end") is None


def test_3_physical_evidence_end_independent_of_recovered_bytes():
    """3. Physical evidence_end strictly reflects candidate boundary, NOT source_offset + recovered_byte_count."""
    # A candidate spanning 200 bytes where only 50 bytes could be recovered (e.g. damaged/truncated)
    cand = Candidate(
        candidate_id="cand-0",
        format="txt",
        mime_type="text/plain",
        category="text",
        offset=100,
        detected_header_length=0,
        estimated_end_offset=300,  # Physical span is 200 bytes
        detection_method="heuristic_text_run",
    )
    # Content has damaged characters at tail
    text_content = b"Line one of verified forensic text\nLine two of verified forensic text\n"
    content = b"\x00" * 100 + text_content + b"\xff" * (300 - 100 - len(text_content)) + b"\x00" * 50

    runs = execute_traced_recoveries("data.bin", content, candidates=[cand], detection_mode="blind")
    assert len(runs) == 1
    run = runs[0]

    # Even if recovered bytes is less than 200, evidence_end must remain exactly 300
    assert run.provenance["evidence_start"] == 100
    assert run.provenance["evidence_end"] == 300
    assert run.provenance["coordinate_system"] == "physical_evidence_offsets"


def test_4_whole_buffer_fallback_coordinates():
    """4. Direct fallback when zero candidates found assigns whole_buffer_fallback coordinates."""
    garbage = b"\x00\x01\x02\x03\x04\x05\x06\x07" * 4  # 32 bytes binary garbage, no signatures
    runs = execute_traced_recoveries("unknown.bin", garbage, detection_mode="blind")
    assert len(runs) == 1
    run = runs[0]

    assert run.provenance["evidence_start"] == 0
    assert run.provenance["evidence_end"] == len(garbage)
    assert run.provenance["coordinate_system"] == "whole_buffer_fallback"
    assert run.provenance["relationships"] == []


# ═════════════════════════════════════════════════════════════════════════════
# 2. CANDIDATE DEDUPLICATION TESTS
# ═════════════════════════════════════════════════════════════════════════════

def test_5_deduplication_exact_offset_and_format_only():
    """5. Deduplication merges only identical (offset, format) pairs; distinct formats at same offset are kept."""
    c_csv = Candidate(
        candidate_id="cand-csv",
        format="csv",
        mime_type="text/csv",
        category="text",
        offset=50,
        detected_header_length=0,
        estimated_end_offset=200,
        detection_method="heuristic_text_run",
    )
    c_txt = Candidate(
        candidate_id="cand-txt",
        format="txt",
        mime_type="text/plain",
        category="text",
        offset=50,
        detected_header_length=0,
        estimated_end_offset=200,
        detection_method="heuristic_text_run",
    )
    # Duplicate CSV candidate at offset 50
    c_csv_dup = Candidate(
        candidate_id="cand-csv-dup",
        format="csv",
        mime_type="text/csv",
        category="text",
        offset=50,
        detected_header_length=0,
        estimated_end_offset=180,
        detection_method="heuristic_text_run",
    )

    deduped = _dedup_candidates([c_csv, c_txt, c_csv_dup])
    # Must preserve both formats (csv and txt) but deduplicate the two csv candidates to 1
    assert len(deduped) == 2
    formats = {c.format for c in deduped}
    assert formats == {"csv", "txt"}


def test_6_deduplication_prefers_known_end():
    """6. Between duplicate (offset, format), known estimated_end_offset is preferred over None."""
    c_unknown = Candidate(
        candidate_id="cand-unknown",
        format="jpeg",
        mime_type="image/jpeg",
        category="image",
        offset=100,
        detected_header_length=2,
        estimated_end_offset=None,
        detection_method="magic_bytes",
    )
    c_known = Candidate(
        candidate_id="cand-known",
        format="jpeg",
        mime_type="image/jpeg",
        category="image",
        offset=100,
        detected_header_length=2,
        estimated_end_offset=500,
        detection_method="magic_bytes",
    )

    deduped = _dedup_candidates([c_unknown, c_known])
    assert len(deduped) == 1
    assert deduped[0].candidate_id == "cand-known"
    assert deduped[0].estimated_end_offset == 500


def test_7_deduplication_prefers_larger_span():
    """7. Between duplicate (offset, format) with known ends, larger physical span is preferred."""
    c_small = Candidate(
        candidate_id="cand-small",
        format="json",
        mime_type="application/json",
        category="structured",
        offset=200,
        detected_header_length=1,
        estimated_end_offset=300,  # span 100
        detection_method="heuristic_json_container",
    )
    c_large = Candidate(
        candidate_id="cand-large",
        format="json",
        mime_type="application/json",
        category="structured",
        offset=200,
        detected_header_length=1,
        estimated_end_offset=450,  # span 250
        detection_method="heuristic_json_container",
    )

    deduped = _dedup_candidates([c_small, c_large])
    assert len(deduped) == 1
    assert deduped[0].candidate_id == "cand-large"
    assert deduped[0].estimated_end_offset == 450


def test_8_deduplication_prefers_larger_header_length():
    """8. Between duplicate (offset, format) with equal spans, larger detected_header_length is preferred."""
    c_hdr1 = Candidate(
        candidate_id="cand-hdr1",
        format="xml",
        mime_type="application/xml",
        category="structured",
        offset=0,
        detected_header_length=1,
        estimated_end_offset=200,
        detection_method="heuristic_xml",
    )
    c_hdr5 = Candidate(
        candidate_id="cand-hdr5",
        format="xml",
        mime_type="application/xml",
        category="structured",
        offset=0,
        detected_header_length=5,
        estimated_end_offset=200,
        detection_method="direct_header",
    )

    deduped = _dedup_candidates([c_hdr1, c_hdr5])
    assert len(deduped) == 1
    assert deduped[0].candidate_id == "cand-hdr5"
    assert deduped[0].detected_header_length == 5


def test_9_deduplication_prefers_higher_method_priority():
    """9. Between duplicate (offset, format) with equal spans and headers, higher method priority is preferred."""
    c_heuristic = Candidate(
        candidate_id="cand-heur",
        format="txt",
        mime_type="text/plain",
        category="text",
        offset=10,
        detected_header_length=0,
        estimated_end_offset=100,
        detection_method="heuristic_text_run",
    )
    c_synthetic = Candidate(
        candidate_id="cand-synth",
        format="txt",
        mime_type="text/plain",
        category="text",
        offset=10,
        detected_header_length=0,
        estimated_end_offset=100,
        detection_method="synthetic_boundary",
    )

    deduped = _dedup_candidates([c_heuristic, c_synthetic])
    assert len(deduped) == 1
    assert deduped[0].candidate_id == "cand-synth"
    assert deduped[0].detection_method == "synthetic_boundary"


# ═════════════════════════════════════════════════════════════════════════════
# 3. SPATIAL RELATIONSHIP TESTS
# ═════════════════════════════════════════════════════════════════════════════

def test_10_spatial_relationship_coextensive():
    """10. Candidates sharing exact start and end offsets receive symmetrical COEXTENSIVE relationship."""
    c_csv = Candidate(
        candidate_id="cand-0",
        format="csv",
        mime_type="text/csv",
        category="text",
        offset=100,
        detected_header_length=0,
        estimated_end_offset=300,
        detection_method="heuristic_text_run",
    )
    c_txt = Candidate(
        candidate_id="cand-1",
        format="txt",
        mime_type="text/plain",
        category="text",
        offset=100,
        detected_header_length=0,
        estimated_end_offset=300,
        detection_method="heuristic_text_run",
    )

    computed = _compute_candidate_relationships([c_csv, c_txt])
    assert len(computed) == 2
    c0 = computed[0]
    c1 = computed[1]

    assert len(c0.relationships) == 1
    assert c0.relationships[0].target_candidate_id == "cand-1"
    assert c0.relationships[0].target_format == "txt"
    assert c0.relationships[0].relationship_type == "COEXTENSIVE"

    assert len(c1.relationships) == 1
    assert c1.relationships[0].target_candidate_id == "cand-0"
    assert c1.relationships[0].target_format == "csv"
    assert c1.relationships[0].relationship_type == "COEXTENSIVE"


def test_11_spatial_relationship_contains_and_contained_by():
    """11. A containing candidate receives CONTAINS while inner candidate receives CONTAINED_BY."""
    outer = Candidate(
        candidate_id="cand-outer",
        format="txt",
        mime_type="text/plain",
        category="text",
        offset=100,
        detected_header_length=0,
        estimated_end_offset=600,
        detection_method="heuristic_text_run",
    )
    inner = Candidate(
        candidate_id="cand-inner",
        format="json",
        mime_type="application/json",
        category="structured",
        offset=200,
        detected_header_length=1,
        estimated_end_offset=400,
        detection_method="heuristic_json_container",
    )

    computed = _compute_candidate_relationships([outer, inner])
    c_out = computed[0]
    c_in = computed[1]

    assert len(c_out.relationships) == 1
    assert c_out.relationships[0].target_candidate_id == "cand-inner"
    assert c_out.relationships[0].relationship_type == "CONTAINS"

    assert len(c_in.relationships) == 1
    assert c_in.relationships[0].target_candidate_id == "cand-outer"
    assert c_in.relationships[0].relationship_type == "CONTAINED_BY"


def test_12_spatial_relationship_overlaps():
    """12. Candidates partially overlapping without containment receive symmetrical OVERLAPS."""
    c_first = Candidate(
        candidate_id="cand-a",
        format="txt",
        mime_type="text/plain",
        category="text",
        offset=100,
        detected_header_length=0,
        estimated_end_offset=300,
        detection_method="heuristic_text_run",
    )
    c_second = Candidate(
        candidate_id="cand-b",
        format="csv",
        mime_type="text/csv",
        category="text",
        offset=200,
        detected_header_length=0,
        estimated_end_offset=400,
        detection_method="heuristic_text_run",
    )

    computed = _compute_candidate_relationships([c_first, c_second])
    ca = computed[0]
    cb = computed[1]

    assert len(ca.relationships) == 1
    assert ca.relationships[0].target_candidate_id == "cand-b"
    assert ca.relationships[0].relationship_type == "OVERLAPS"

    assert len(cb.relationships) == 1
    assert cb.relationships[0].target_candidate_id == "cand-a"
    assert cb.relationships[0].relationship_type == "OVERLAPS"


def test_13_spatial_relationship_disjoint():
    """13. Disjoint candidates have no asserted relationships."""
    c1 = Candidate(
        candidate_id="cand-1",
        format="png",
        mime_type="image/png",
        category="image",
        offset=0,
        detected_header_length=8,
        estimated_end_offset=100,
        detection_method="magic_bytes",
    )
    c2 = Candidate(
        candidate_id="cand-2",
        format="jpeg",
        mime_type="image/jpeg",
        category="image",
        offset=100,  # Abutting or subsequent
        detected_header_length=2,
        estimated_end_offset=250,
        detection_method="magic_bytes",
    )

    computed = _compute_candidate_relationships([c1, c2])
    assert len(computed[0].relationships) == 0
    assert len(computed[1].relationships) == 0


def test_14_unknown_boundary_prohibits_all_relationships():
    """14. Invariant: If either candidate has unknown end (None), no spatial relationship is asserted."""
    c_known = Candidate(
        candidate_id="cand-known",
        format="json",
        mime_type="application/json",
        category="structured",
        offset=100,
        detected_header_length=1,
        estimated_end_offset=300,
        detection_method="heuristic_json_container",
    )
    c_unknown = Candidate(
        candidate_id="cand-unknown",
        format="png",
        mime_type="image/png",
        category="image",
        offset=100,  # Same start! But end is unknown
        detected_header_length=8,
        estimated_end_offset=None,
        detection_method="magic_bytes",
    )

    computed = _compute_candidate_relationships([c_known, c_unknown])
    # Because one end is unknown, containment/coextensiveness cannot be proven
    assert len(computed[0].relationships) == 0
    assert len(computed[1].relationships) == 0


# ═════════════════════════════════════════════════════════════════════════════
# 4. POST-DISCOVERY CANDIDATE PROCESSING CAP (MAX_CANDIDATES = 250)
# ═════════════════════════════════════════════════════════════════════════════

def test_15_candidate_cap_enforcement_at_250():
    """15. Candidate cap of 250 retains first 250 and records omitted count in metadata."""
    # Create evidence buffer with 300 synthetic artifact candidates
    # Each is a valid small JSON object surrounded by synthetic markers
    parts = []
    for i in range(300):
        body = f'{{"idx": {i}, "tag": "test_{i}"}}'.encode("utf-8")
        parts.append(b"[SYNTHETIC_ARTIFACT_START]" + body + b"[SYNTHETIC_ARTIFACT_END]")
    evidence = b"".join(parts)

    candidates = scan_evidence(evidence)
    assert len(candidates) == MAX_CANDIDATES
    assert len(candidates) == 250

    meta = get_last_scan_metadata()
    assert meta["candidate_cap_enforced"] is True
    assert meta["total_discovered_candidates"] == 300
    assert meta["candidates_omitted"] == 50


def test_16_candidate_cap_not_enforced_under_threshold():
    """16. Under threshold <= 250, candidate_cap_enforced is False and candidates_omitted is 0."""
    parts = []
    for i in range(5):
        body = f'{{"idx": {i}, "tag": "test_{i}"}}'.encode("utf-8")
        parts.append(b"[SYNTHETIC_ARTIFACT_START]" + body + b"[SYNTHETIC_ARTIFACT_END]")
    evidence = b"".join(parts)

    candidates = scan_evidence(evidence)
    assert len(candidates) == 5

    meta = get_last_scan_metadata()
    assert meta["candidate_cap_enforced"] is False
    assert meta["total_discovered_candidates"] == 5
    assert meta["candidates_omitted"] == 0


def test_17_candidate_cap_trace_event_and_provenance():
    """17. Traced recovery when cap is enforced emits SCANNING_COMPLETED event and propagates metadata."""
    # Pass 260 candidates directly into execute_traced_recoveries
    dummy_cands = [
        Candidate(
            candidate_id=f"c-{i}",
            format="txt",
            mime_type="text/plain",
            category="text",
            offset=i * 10,
            detected_header_length=0,
            estimated_end_offset=(i * 10) + 8,
            detection_method="heuristic_text_run",
        )
        for i in range(260)
    ]
    content = b"A" * 3000

    runs = execute_traced_recoveries("cap_test.raw", content, candidates=dummy_cands, detection_mode="blind")
    assert len(runs) == 250

    sample_run = runs[0]
    assert sample_run.provenance["candidate_cap_enforced"] is True
    assert sample_run.provenance["total_discovered_candidates"] == 260
    assert sample_run.provenance["candidates_omitted"] == 10

    # Verify SCANNING_COMPLETED warning event
    cap_events = [e for e in sample_run.events if e.event_type == "SCANNING_COMPLETED"]
    assert len(cap_events) >= 1
    assert "Candidate cap enforced" in cap_events[0].message
    assert "250" in cap_events[0].message


# ═════════════════════════════════════════════════════════════════════════════
# 5. PROVENANCE & EVENT PROPAGATION TESTS
# ═════════════════════════════════════════════════════════════════════════════

def test_18_relationships_propagated_to_provenance_and_events():
    """18. Relationships computed by scanner are faithfully reflected in run.provenance and CANDIDATE_FOUND."""
    # Create evidence buffer with a CSV and TXT coextensive at offset 10
    csv_bytes = b"id,name,role,status\n101,Alice,admin,active\n102,Bob,user,pending\n103,Charlie,auditor,active\n"
    evidence = b"\x00" * 10 + csv_bytes + b"\x00" * 20

    runs = execute_traced_recoveries("multi_run.raw", evidence, detection_mode="blind")
    # Must have both CSV and TXT candidates evaluated
    assert len(runs) >= 2
    csv_run = next(r for r in runs if r.format == "csv")
    txt_run = next(r for r in runs if r.format == "txt")

    assert "relationships" in csv_run.provenance
    csv_rels = csv_run.provenance["relationships"]
    assert any(r["target_format"] == "txt" for r in csv_rels)

    assert "relationships" in txt_run.provenance
    txt_rels = txt_run.provenance["relationships"]
    assert any(r["target_format"] == "csv" for r in txt_rels)

    # Check CANDIDATE_FOUND event contains relationships
    evt = next(e for e in csv_run.events if e.event_type == "CANDIDATE_FOUND")
    assert "relationships" in (evt.relevant_artifact_info or {})


# ═════════════════════════════════════════════════════════════════════════════
# 6. BLIND MULTI-FORMAT UNSUPPRESSED DISCOVERY TESTS
# ═════════════════════════════════════════════════════════════════════════════

def test_19_blind_multi_format_unsuppressed_discovery():
    """19. Blind mode on a composite buffer discovers independent candidates without format suppression."""
    # Composite buffer containing:
    # 1. Valid JSON object
    # 2. Valid CSV table
    # 3. Valid XML document
    json_doc = b'{"case_id": "REC-777", "analyst": "Sherlock", "count": 3, "verified": true}\n'
    csv_doc = b"date,metric,val,alert\n2026-09-01,temp,72,none\n2026-09-02,temp,85,high\n2026-09-03,temp,68,none\n"
    xml_doc = b'<?xml version="1.0"?><report><id>R1</id><status>CLOSED</status></report>'

    evidence = (
        b"\x00" * 32
        + json_doc
        + b"\x00" * 32
        + csv_doc
        + b"\x00" * 32
        + xml_doc
        + b"\x00" * 32
    )

    runs = execute_traced_recoveries("composite_evidence.raw", evidence, detection_mode="blind")
    recovered_formats = {r.format for r in runs}

    assert "json" in recovered_formats
    assert "csv" in recovered_formats
    assert "xml" in recovered_formats
    assert len(runs) >= 3


def test_20_known_file_mode_preserves_format_hint():
    """20. Known file mode preserves format-hint filtering for single-format analysis."""
    json_doc = b'{"target": "single_format", "flag": true}\n'
    csv_doc = b"a,b,c\n1,2,3\n4,5,6\n"
    evidence = b"\x00" * 20 + json_doc + b"\x00" * 20 + csv_doc

    # When user uploads as "document.json" in known_file mode, non-json candidates are filtered
    runs = execute_traced_recoveries("document.json", evidence, detection_mode="known_file")
    recovered_formats = {r.format for r in runs}

    assert "json" in recovered_formats
    assert "csv" not in recovered_formats


# ═════════════════════════════════════════════════════════════════════════════
# 7. BIFRAGMENT & ERROR RUN TESTS
# ═════════════════════════════════════════════════════════════════════════════

def test_21_bifragment_pair_coordinates_and_provenance():
    """21. Bifragment pair maintains physical coordinates and bifragment_offsets without altering gap logic."""
    cand1 = Candidate(
        candidate_id="cand-0",
        format="png",
        mime_type="image/png",
        category="image",
        offset=50,
        detected_header_length=8,
        estimated_end_offset=None,
        detection_method="magic_bytes",
    )
    cand2 = Candidate(
        candidate_id="cand-1",
        format="png",
        mime_type="image/png",
        category="image",
        offset=300,
        detected_header_length=8,
        estimated_end_offset=None,
        detection_method="magic_bytes",
    )
    content = b"\x00" * 50 + PNG_SIGNATURE + b"fragA" + b"\x00" * (300 - 50 - 13) + PNG_SIGNATURE + b"fragB"

    runs = execute_traced_recoveries("bifrag.raw", content, candidates=[cand1, cand2], detection_mode="blind")
    assert len(runs) == 1
    run = runs[0]

    assert run.provenance["evidence_start"] == 50
    assert run.provenance["evidence_end"] is None
    assert run.provenance["coordinate_system"] == "physical_evidence_offsets"
    assert run.provenance["bifragment_offsets"] == [50, 300]


def test_22_error_run_preserves_physical_coordinates():
    """22. Failure isolation preserves candidate physical coordinates in error recovery runs."""
    cand = Candidate(
        candidate_id="cand-bad",
        format="json",
        mime_type="application/json",
        category="structured",
        offset=150,
        detected_header_length=1,
        estimated_end_offset=300,
        detection_method="heuristic_json_container",
    )

    from backend.app.recovery.tracer import _create_error_recovery_run
    err_run = _create_error_recovery_run(
        filename="test.raw",
        cand=cand,
        error=RuntimeError("Simulated forensic extraction failure"),
        detection_mode="blind",
    )

    assert err_run.status == "UNRECOVERABLE"
    assert err_run.provenance["evidence_start"] == 150
    assert err_run.provenance["evidence_end"] == 300
    assert err_run.provenance["coordinate_system"] == "physical_evidence_offsets"
    assert "Simulated forensic extraction failure" in err_run.provenance["error"]


def test_23_sqlite_persistence_roundtrip_with_m33_provenance():
    """23. Full RecoveryRun with Milestone 3.3.3 provenance persists to SQLite and reloads cleanly."""
    cand = Candidate(
        candidate_id="cand-persist",
        format="json",
        mime_type="application/json",
        category="structured",
        offset=64,
        detected_header_length=1,
        estimated_end_offset=256,
        detection_method="heuristic_json_container",
    )
    json_bytes = b'{"case": "SQLITE-TEST", "active": true}\n'
    content = b"\x00" * 64 + json_bytes + b"\x00" * (256 - 64 - len(json_bytes))

    runs = execute_traced_recoveries("persist.raw", content, candidates=[cand], detection_mode="blind")
    assert len(runs) == 1
    original_run = runs[0]

    # Reload from store
    loaded_run = store.get_recovery_run(original_run.run_id)
    assert loaded_run is not None
    assert loaded_run.provenance["evidence_start"] == 64
    assert loaded_run.provenance["evidence_end"] == 256
    assert loaded_run.provenance["coordinate_system"] == "physical_evidence_offsets"
    assert loaded_run.provenance["detection_method"] == "heuristic_json_container"
