"""
test_evidence_graph_m34.py — Comprehensive test suite for Recoverix Milestone 3.4.

Tests:
  1. Empty graph
  2. Single candidate
  3. Disjoint candidates
  4. Touching candidates (A.end == B.start are disjoint)
  5. Coextensive candidates
  6. Strict containment (CONTAINS / CONTAINED_BY)
  7. Partial overlap (OVERLAPS)
  8. Overlap chain (transitive clustering)
  9. Nested containment (containment tree)
  10. Format collision on coextensive span (is_ambiguous=True)
  11. Unknown end (evidence_end is None -> zero edges, cluster_end is None)
  12. Candidate cap enforced
  13. No phantom nodes for omitted candidates
  14. Deterministic repeated execution
  15. Identity lineage (candidate_id optional, no fake candidate IDs)
  16. SQLite restart round-trip
  17. V/R/M preservation
  18. Confidence scale preservation (0.0–100.0)
  19. Bifragment behavior
  20. Blind multi-format behavior
  21. Authoritative provenance ID assigns correct buffer
  22. Missing provenance + present filename -> evidence_file_id=None
  23. Same filename without authoritative ID -> never coextensive
  24. Unknown-scope nodes produce zero edges
  25. Unknown-scope nodes form isolated clusters
  26. Cross-buffer cluster isolation
  27. Mixed relationship cluster classification
  28. Containment without ambiguity (structural nesting)
  29. Coextensive ambiguity
  30. Pydantic model immutability
  31. API endpoint GET /api/cases/{case_id}/graph
"""

from __future__ import annotations

import tempfile
import pytest
from datetime import datetime, timezone
from typing import Optional
from pydantic import ValidationError
from fastapi.testclient import TestClient

from backend.app.models.recovery_run import RecoveryRun
from backend.app.models.case import CaseCreate
from backend.app.models.artifact import ArtifactResponse
from backend.app.models.evidence_graph import (
    GraphNode,
    GraphEdge,
    ArtifactCluster,
    EvidenceGraph,
)
from backend.app.recovery.graph import (
    resolve_evidence_file_id,
    classify_cluster_relationships,
    build_evidence_graph_from_runs,
    build_case_evidence_graph,
)
from backend.app.storage.sqlite_engine import SqliteEngine
from backend.app.storage.sqlite_store import SqliteStore
from backend.app.main import app


def _make_test_run(
    run_id: str,
    format: str = "png",
    evidence_start: int = 0,
    evidence_end: Optional[int] = 100,
    evidence_file_id: Optional[str] = "ev_01",
    candidate_id: Optional[str] = None,
    artifact_id: Optional[str] = None,
    status: str = "FULLY_RECOVERED",
    confidence_score: float = 95.0,
    verified_bytes: int = 100,
    reconstructed_bytes: int = 0,
    missing_bytes: int = 0,
    detection_method: str = "magic_bytes",
    case_id: Optional[str] = "case_test_01",
    filename: str = "evidence.img",
) -> RecoveryRun:
    """Helper to construct canonical RecoveryRun models with physical coordinates."""
    prov = {
        "evidence_start": evidence_start,
        "coordinate_system": "physical_evidence_offsets" if evidence_end is not None else "whole_buffer_fallback",
        "detection_method": detection_method,
    }
    if evidence_end is not None:
        prov["evidence_end"] = evidence_end
    if evidence_file_id is not None:
        prov["evidence_file_id"] = evidence_file_id
    if case_id is not None:
        prov["case_id"] = case_id

    now = datetime.now(timezone.utc)
    return RecoveryRun(
        run_id=run_id,
        case_id=case_id,
        artifact_id=artifact_id,
        candidate_id=candidate_id,
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


# ═════════════════════════════════════════════════════════════════════════════
# 1. Empty Graph
# ═════════════════════════════════════════════════════════════════════════════

def test_01_empty_graph():
    graph = build_evidence_graph_from_runs(runs=[], case_id="case_empty")
    assert graph.nodes == []
    assert graph.edges == []
    assert graph.clusters == []
    assert graph.evidence_buffers == []
    assert graph.metadata.total_nodes == 0
    assert graph.metadata.total_edges == 0
    assert graph.metadata.total_clusters == 0
    assert graph.metadata.graph_is_complete is True


# ═════════════════════════════════════════════════════════════════════════════
# 2. Single Candidate
# ═════════════════════════════════════════════════════════════════════════════

def test_02_single_candidate():
    run = _make_test_run(
        run_id="run_single",
        evidence_start=100,
        evidence_end=500,
        evidence_file_id="ev_01",
        candidate_id="cand_1",
    )
    graph = build_evidence_graph_from_runs([run])

    assert len(graph.nodes) == 1
    assert graph.nodes[0].node_id == "node_run_single"
    assert graph.nodes[0].candidate_id == "cand_1"
    assert graph.nodes[0].evidence_start == 100
    assert graph.nodes[0].evidence_end == 500
    assert graph.edges == []

    assert len(graph.clusters) == 1
    c = graph.clusters[0]
    assert c.cluster_start == 100
    assert c.cluster_end == 500
    assert c.node_ids == ["node_run_single"]
    assert c.relationship_classification == "ISOLATED"
    assert c.has_ambiguity is False


# ═════════════════════════════════════════════════════════════════════════════
# 3. Disjoint Candidates
# ═════════════════════════════════════════════════════════════════════════════

def test_03_disjoint_candidates():
    r1 = _make_test_run("run_1", evidence_start=100, evidence_end=200, evidence_file_id="ev_01")
    r2 = _make_test_run("run_2", evidence_start=300, evidence_end=400, evidence_file_id="ev_01")
    graph = build_evidence_graph_from_runs([r1, r2])

    assert len(graph.nodes) == 2
    assert len(graph.edges) == 0
    assert len(graph.clusters) == 2
    for c in graph.clusters:
        assert c.relationship_classification == "ISOLATED"


# ═════════════════════════════════════════════════════════════════════════════
# 4. Touching Candidates (A.end == B.start are Disjoint)
# ═════════════════════════════════════════════════════════════════════════════

def test_04_touching_candidates_are_disjoint():
    r1 = _make_test_run("run_1", evidence_start=100, evidence_end=200, evidence_file_id="ev_01")
    r2 = _make_test_run("run_2", evidence_start=200, evidence_end=300, evidence_file_id="ev_01")
    graph = build_evidence_graph_from_runs([r1, r2])

    # Touching intervals share exactly 0 bytes in half-open [100, 200) and [200, 300)
    assert len(graph.edges) == 0
    assert len(graph.clusters) == 2
    assert graph.clusters[0].relationship_classification == "ISOLATED"
    assert graph.clusters[1].relationship_classification == "ISOLATED"


# ═════════════════════════════════════════════════════════════════════════════
# 5. Coextensive Candidates
# ═════════════════════════════════════════════════════════════════════════════

def test_05_coextensive_candidates():
    r1 = _make_test_run("run_1", format="png", evidence_start=100, evidence_end=500, evidence_file_id="ev_01")
    r2 = _make_test_run("run_2", format="png", evidence_start=100, evidence_end=500, evidence_file_id="ev_01")
    graph = build_evidence_graph_from_runs([r1, r2])

    assert len(graph.nodes) == 2
    assert len(graph.edges) == 2  # Bidirectional

    edge_types = {e.relationship_type for e in graph.edges}
    assert edge_types == {"COEXTENSIVE"}
    for e in graph.edges:
        assert e.overlap_start == 100
        assert e.overlap_end == 500
        assert e.overlap_bytes == 400

    assert len(graph.clusters) == 1
    assert graph.clusters[0].relationship_classification == "COEXTENSIVE_SET"
    assert graph.clusters[0].total_nodes == 2


# ═════════════════════════════════════════════════════════════════════════════
# 6. Strict Containment
# ═════════════════════════════════════════════════════════════════════════════

def test_06_strict_containment():
    outer = _make_test_run("run_outer", format="xml", evidence_start=100, evidence_end=1000, evidence_file_id="ev_01")
    inner = _make_test_run("run_inner", format="jpeg", evidence_start=200, evidence_end=400, evidence_file_id="ev_01")
    graph = build_evidence_graph_from_runs([outer, inner])

    assert len(graph.nodes) == 2
    assert len(graph.edges) == 2

    e_out = next(e for e in graph.edges if e.source_node_id == "node_run_outer")
    e_in = next(e for e in graph.edges if e.source_node_id == "node_run_inner")

    assert e_out.relationship_type == "CONTAINS"
    assert e_out.target_node_id == "node_run_inner"
    assert e_out.overlap_start == 200
    assert e_out.overlap_end == 400
    assert e_out.overlap_bytes == 200

    assert e_in.relationship_type == "CONTAINED_BY"
    assert e_in.target_node_id == "node_run_outer"

    assert len(graph.clusters) == 1
    assert graph.clusters[0].relationship_classification == "CONTAINMENT_TREE"


# ═════════════════════════════════════════════════════════════════════════════
# 7. Partial Overlap
# ═════════════════════════════════════════════════════════════════════════════

def test_07_partial_overlap():
    r1 = _make_test_run("run_1", evidence_start=100, evidence_end=500, evidence_file_id="ev_01")
    r2 = _make_test_run("run_2", evidence_start=300, evidence_end=800, evidence_file_id="ev_01")
    graph = build_evidence_graph_from_runs([r1, r2])

    assert len(graph.nodes) == 2
    assert len(graph.edges) == 2  # Bidirectional OVERLAPS

    for e in graph.edges:
        assert e.relationship_type == "OVERLAPS"
        assert e.overlap_start == 300
        assert e.overlap_end == 500
        assert e.overlap_bytes == 200

    assert len(graph.clusters) == 1
    assert graph.clusters[0].relationship_classification == "OVERLAP_SPAN"
    assert graph.clusters[0].cluster_start == 100
    assert graph.clusters[0].cluster_end == 800


# ═════════════════════════════════════════════════════════════════════════════
# 8. Overlap Chain (Transitive Clustering)
# ═════════════════════════════════════════════════════════════════════════════

def test_08_overlap_chain():
    # A overlaps B, B overlaps C, but A and C are disjoint
    rA = _make_test_run("run_A", evidence_start=100, evidence_end=300, evidence_file_id="ev_01")
    rB = _make_test_run("run_B", evidence_start=200, evidence_end=500, evidence_file_id="ev_01")
    rC = _make_test_run("run_C", evidence_start=400, evidence_end=700, evidence_file_id="ev_01")
    graph = build_evidence_graph_from_runs([rA, rB, rC])

    assert len(graph.nodes) == 3
    # 2 edges for A <-> B, 2 edges for B <-> C = 4 edges total
    assert len(graph.edges) == 4

    # Disjoint set union unites all 3 into 1 cluster
    assert len(graph.clusters) == 1
    c = graph.clusters[0]
    assert c.total_nodes == 3
    assert c.cluster_start == 100
    assert c.cluster_end == 700
    assert c.relationship_classification == "OVERLAP_SPAN"


# ═════════════════════════════════════════════════════════════════════════════
# 9. Nested Containment
# ═════════════════════════════════════════════════════════════════════════════

def test_09_nested_containment():
    rA = _make_test_run("run_A", format="xml", evidence_start=100, evidence_end=1000, evidence_file_id="ev_01")
    rB = _make_test_run("run_B", format="json", evidence_start=200, evidence_end=800, evidence_file_id="ev_01")
    rC = _make_test_run("run_C", format="jpeg", evidence_start=300, evidence_end=500, evidence_file_id="ev_01")
    graph = build_evidence_graph_from_runs([rA, rB, rC])

    assert len(graph.nodes) == 3
    # A contains B and C (4 edges), B contains C (2 edges) = 6 edges
    assert len(graph.edges) == 6
    assert len(graph.clusters) == 1
    assert graph.clusters[0].relationship_classification == "CONTAINMENT_TREE"


# ═════════════════════════════════════════════════════════════════════════════
# 10. Format Collision on Coextensive Span
# ═════════════════════════════════════════════════════════════════════════════

def test_10_format_collision_coextensive_ambiguity():
    r_csv = _make_test_run("run_csv", format="csv", evidence_start=100, evidence_end=300, evidence_file_id="ev_01")
    r_txt = _make_test_run("run_txt", format="txt", evidence_start=100, evidence_end=300, evidence_file_id="ev_01")
    graph = build_evidence_graph_from_runs([r_csv, r_txt])

    # Competing formats at same physical span must set is_ambiguous=True
    for node in graph.nodes:
        assert node.is_ambiguous is True

    assert len(graph.clusters) == 1
    assert graph.clusters[0].has_ambiguity is True


# ═════════════════════════════════════════════════════════════════════════════
# 11. Unknown Boundary (evidence_end is None)
# ═════════════════════════════════════════════════════════════════════════════

def test_11_unknown_boundary_protection():
    r_unknown = _make_test_run("run_unk", evidence_start=100, evidence_end=None, evidence_file_id="ev_01")
    r_known = _make_test_run("run_known", evidence_start=100, evidence_end=500, evidence_file_id="ev_01")
    graph = build_evidence_graph_from_runs([r_unknown, r_known])

    # Unknown boundary never produces spatial edges
    assert len(graph.edges) == 0
    assert len(graph.clusters) == 2

    unk_cluster = next(c for c in graph.clusters if "node_run_unk" in c.node_ids)
    assert unk_cluster.cluster_start == 100
    # P2 Invariant: cluster_end must be None, NEVER cluster_start
    assert unk_cluster.cluster_end is None


# ═════════════════════════════════════════════════════════════════════════════
# 12. Candidate Cap Enforced
# ═════════════════════════════════════════════════════════════════════════════

def test_12_candidate_cap_enforced():
    runs = [_make_test_run(f"run_{i}", evidence_start=i*10, evidence_end=(i+1)*10, evidence_file_id="ev_01") for i in range(10)]
    cap_meta = {
        "ev_01": {
            "candidate_cap_enforced": True,
            "total_discovered_candidates": 300,
            "candidates_omitted": 50,
        }
    }
    graph = build_evidence_graph_from_runs(runs, candidate_cap_metadata=cap_meta)

    assert graph.metadata.candidate_cap_enforced is True
    assert graph.metadata.graph_is_complete is False
    assert graph.metadata.total_discovered_candidates == 300
    assert graph.metadata.candidates_omitted == 50

    buf = graph.evidence_buffers[0]
    assert buf.candidate_cap_enforced is True
    assert buf.buffer_is_complete is False
    assert buf.candidates_omitted == 50


# ═════════════════════════════════════════════════════════════════════════════
# 13. Zero Phantom Nodes
# ═════════════════════════════════════════════════════════════════════════════

def test_13_no_phantom_nodes():
    runs = [
        _make_test_run(
            f"run_{i}",
            evidence_start=i * 100,
            evidence_end=(i + 1) * 100,
            evidence_file_id="ev_01",
        )
        for i in range(5)
    ]
    cap_meta = {
        "candidate_cap_enforced": True,
        "total_discovered_candidates": 255,
        "candidates_omitted": 250,
    }
    graph = build_evidence_graph_from_runs(runs, candidate_cap_metadata=cap_meta)

    # Only the 5 evaluated runs are nodes; zero phantom nodes fabricated
    assert len(graph.nodes) == 5
    assert len(graph.clusters) == 5


# ═════════════════════════════════════════════════════════════════════════════
# 14. Deterministic Repeated Execution
# ═════════════════════════════════════════════════════════════════════════════

def test_14_deterministic_execution():
    r1 = _make_test_run("run_1", evidence_start=100, evidence_end=300, evidence_file_id="ev_01")
    r2 = _make_test_run("run_2", evidence_start=200, evidence_end=400, evidence_file_id="ev_01")

    g1 = build_evidence_graph_from_runs([r1, r2])
    g2 = build_evidence_graph_from_runs([r2, r1])  # Order reversed

    assert g1.model_dump_json() == g2.model_dump_json()


# ═════════════════════════════════════════════════════════════════════════════
# 15. Identity Lineage & Optional Candidate ID
# ═════════════════════════════════════════════════════════════════════════════

def test_15_identity_lineage_and_optional_candidate_id():
    r_scanner = _make_test_run("run_scan", candidate_id="cand_real_01", artifact_id="art_01", evidence_file_id="ev_01")
    r_fallback = _make_test_run("run_fb", candidate_id=None, artifact_id=None, evidence_file_id="ev_01")

    graph = build_evidence_graph_from_runs([r_scanner, r_fallback])

    n_scan = next(n for n in graph.nodes if n.run_id == "run_scan")
    n_fb = next(n for n in graph.nodes if n.run_id == "run_fb")

    assert n_scan.node_id == "node_run_scan"
    assert n_scan.candidate_id == "cand_real_01"
    assert n_scan.artifact_id == "art_01"

    assert n_fb.node_id == "node_run_fb"
    # Invariant: candidate_id must be None, NEVER cand_run_fb
    assert n_fb.candidate_id is None
    assert n_fb.artifact_id is None


# ═════════════════════════════════════════════════════════════════════════════
# 16. SQLite Restart Round-Trip
# ═════════════════════════════════════════════════════════════════════════════

def test_16_sqlite_restart_round_trip():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = tmp.name
        engine = SqliteEngine(db_path)
        store = SqliteStore(engine)

        case = store.create_case("Case Persist Test")
        run = _make_test_run("run_persist_1", case_id=case.case_id, evidence_file_id="ev_db_01")
        store.add_recovery_run(run)

        # Build initial graph
        g_before = build_case_evidence_graph(case.case_id, store)

        # Close and reopen store
        store.close()
        store_new = SqliteStore(db_path)

        g_after = build_case_evidence_graph(case.case_id, store_new)
        store_new.close()

        assert g_before.model_dump_json() == g_after.model_dump_json()


# ═════════════════════════════════════════════════════════════════════════════
# 17. V/R/M Metrics Preservation
# ═════════════════════════════════════════════════════════════════════════════

def test_17_v_r_m_metrics_preservation():
    run = _make_test_run("run_vrm", verified_bytes=500, reconstructed_bytes=200, missing_bytes=50)
    graph = build_evidence_graph_from_runs([run])

    node = graph.nodes[0]
    assert node.verified_bytes == 500
    assert node.reconstructed_bytes == 200
    assert node.missing_bytes == 50


# ═════════════════════════════════════════════════════════════════════════════
# 18. Confidence Scale Preservation (0.0–100.0)
# ═════════════════════════════════════════════════════════════════════════════

def test_18_confidence_scale_preservation():
    run = _make_test_run("run_conf", confidence_score=92.5)
    graph = build_evidence_graph_from_runs([run])

    node = graph.nodes[0]
    # Invariant: 0.0–100.0 scale preserved without normalization to [0.0, 1.0]
    assert node.confidence_score == 92.5


# ═════════════════════════════════════════════════════════════════════════════
# 19. Bifragment Behavior
# ═════════════════════════════════════════════════════════════════════════════

def test_19_bifragment_behavior():
    run = _make_test_run(
        "run_bifrag",
        format="csv",
        evidence_start=100,
        evidence_end=800,
        evidence_file_id="ev_01",
        reconstructed_bytes=150,
        detection_method="bifragment_gap",
    )
    graph = build_evidence_graph_from_runs([run])

    node = graph.nodes[0]
    assert node.detection_method == "bifragment_gap"
    assert node.reconstructed_bytes == 150
    assert node.evidence_start == 100
    assert node.evidence_end == 800


# ═════════════════════════════════════════════════════════════════════════════
# 20. Blind Multi-Format Coverage
# ═════════════════════════════════════════════════════════════════════════════

def test_20_blind_multiformat_coverage():
    formats = ["json", "xml", "txt", "csv", "png", "jpeg", "pdf"]
    runs = [
        _make_test_run(f"run_{fmt}", format=fmt, evidence_start=i*100, evidence_end=(i+1)*100, evidence_file_id="ev_01")
        for i, fmt in enumerate(formats)
    ]
    graph = build_evidence_graph_from_runs(runs)

    assert len(graph.nodes) == 7
    graph_formats = {n.format for n in graph.nodes}
    assert graph_formats == set(formats)


# ═════════════════════════════════════════════════════════════════════════════
# 21. Authoritative Provenance ID Assigns Correct Buffer
# ═════════════════════════════════════════════════════════════════════════════

def test_21_authoritative_provenance_id():
    run = _make_test_run("run_auth", evidence_file_id="ev_authoritative_99")
    graph = build_evidence_graph_from_runs([run])

    assert graph.nodes[0].evidence_file_id == "ev_authoritative_99"
    assert len(graph.evidence_buffers) == 1
    assert graph.evidence_buffers[0].evidence_file_id == "ev_authoritative_99"


# ═════════════════════════════════════════════════════════════════════════════
# 22. Missing Provenance ID + Present Filename -> None
# ═════════════════════════════════════════════════════════════════════════════

def test_22_missing_provenance_plus_filename_is_none():
    run = _make_test_run("run_no_prov", evidence_file_id=None, filename="dump.raw")
    graph = build_evidence_graph_from_runs([run])

    # Invariant: Must NOT fallback to filename!
    assert graph.nodes[0].evidence_file_id is None
    # Buffer summary is only created for authoritative non-None evidence_file_ids
    assert len(graph.evidence_buffers) == 0


# ═════════════════════════════════════════════════════════════════════════════
# 23. Same Filename Without Authoritative ID -> Never Coextensive
# ═════════════════════════════════════════════════════════════════════════════

def test_23_same_filename_without_authoritative_id_never_coextensive():
    r1 = _make_test_run("run_1", evidence_start=100, evidence_end=500, evidence_file_id=None, filename="shared_disk.img")
    r2 = _make_test_run("run_2", evidence_start=100, evidence_end=500, evidence_file_id=None, filename="shared_disk.img")
    graph = build_evidence_graph_from_runs([r1, r2])

    assert r1.provenance.get("evidence_file_id") is None
    assert r2.provenance.get("evidence_file_id") is None
    assert graph.nodes[0].evidence_file_id is None
    assert graph.nodes[1].evidence_file_id is None

    # Unknown coordinate scope nodes must NEVER form edges, even with identical coordinates
    assert len(graph.edges) == 0


# ═════════════════════════════════════════════════════════════════════════════
# 24. Unknown Scope Zero Edges
# ═════════════════════════════════════════════════════════════════════════════

def test_24_unknown_scope_zero_edges():
    r_unscoped = _make_test_run("run_u", evidence_start=100, evidence_end=500, evidence_file_id=None)
    r_scoped = _make_test_run("run_s", evidence_start=100, evidence_end=500, evidence_file_id="ev_01")
    graph = build_evidence_graph_from_runs([r_unscoped, r_scoped])

    assert len(graph.edges) == 0


# ═════════════════════════════════════════════════════════════════════════════
# 25. Unknown Scope Isolated Clusters
# ═════════════════════════════════════════════════════════════════════════════

def test_25_unknown_scope_isolated_clusters():
    r1 = _make_test_run("run_u1", evidence_start=100, evidence_end=500, evidence_file_id=None)
    r2 = _make_test_run("run_u2", evidence_start=100, evidence_end=500, evidence_file_id=None)
    graph = build_evidence_graph_from_runs([r1, r2])

    # Unscoped nodes never enter a shared cluster
    assert len(graph.clusters) == 2
    for c in graph.clusters:
        assert c.evidence_file_id is None
        assert c.relationship_classification == "ISOLATED"
        assert c.total_nodes == 1


# ═════════════════════════════════════════════════════════════════════════════
# 26. Cross-Buffer Cluster Isolation
# ═════════════════════════════════════════════════════════════════════════════

def test_26_cross_buffer_cluster_isolation():
    r_bufA = _make_test_run("run_A", evidence_start=100, evidence_end=500, evidence_file_id="buf_A")
    r_bufB = _make_test_run("run_B", evidence_start=100, evidence_end=500, evidence_file_id="buf_B")
    graph = build_evidence_graph_from_runs([r_bufA, r_bufB])

    assert len(graph.edges) == 0
    assert len(graph.clusters) == 2
    assert graph.clusters[0].evidence_file_id != graph.clusters[1].evidence_file_id


# ═════════════════════════════════════════════════════════════════════════════
# 27. Mixed Relationship Cluster Classification
# ═════════════════════════════════════════════════════════════════════════════

def test_27_mixed_relationship_cluster_classification():
    # A contains B, B overlaps C
    # A: [100, 1000), B: [200, 500), C: [400, 700)
    rA = _make_test_run("run_A", evidence_start=100, evidence_end=1000, evidence_file_id="ev_01")
    rB = _make_test_run("run_B", evidence_start=200, evidence_end=500, evidence_file_id="ev_01")
    rC = _make_test_run("run_C", evidence_start=400, evidence_end=700, evidence_file_id="ev_01")

    graph = build_evidence_graph_from_runs([rA, rB, rC])

    # Containment + Overlap present in same cluster -> MIXED
    assert len(graph.clusters) == 1
    assert graph.clusters[0].relationship_classification == "MIXED"


# ═════════════════════════════════════════════════════════════════════════════
# 28. Containment Without Ambiguity
# ═════════════════════════════════════════════════════════════════════════════

def test_28_containment_without_ambiguity():
    # XML document containing an embedded JPEG thumbnail
    r_xml = _make_test_run("run_xml", format="xml", evidence_start=100, evidence_end=1000, evidence_file_id="ev_01")
    r_jpg = _make_test_run("run_jpg", format="jpeg", evidence_start=300, evidence_end=600, evidence_file_id="ev_01")

    graph = build_evidence_graph_from_runs([r_xml, r_jpg])

    # Pure containment must NOT trigger ambiguity
    assert graph.nodes[0].is_ambiguous is False
    assert graph.nodes[1].is_ambiguous is False
    assert graph.clusters[0].has_ambiguity is False


# ═════════════════════════════════════════════════════════════════════════════
# 29. Coextensive Ambiguity
# ═════════════════════════════════════════════════════════════════════════════

def test_29_coextensive_ambiguity():
    r1 = _make_test_run("run_1", format="json", evidence_start=100, evidence_end=500, evidence_file_id="ev_01")
    r2 = _make_test_run("run_2", format="xml", evidence_start=100, evidence_end=500, evidence_file_id="ev_01")

    graph = build_evidence_graph_from_runs([r1, r2])

    assert graph.nodes[0].is_ambiguous is True
    assert graph.nodes[1].is_ambiguous is True
    assert graph.clusters[0].has_ambiguity is True


# ═════════════════════════════════════════════════════════════════════════════
# 30. Pydantic Model Immutability
# ═════════════════════════════════════════════════════════════════════════════

def test_30_pydantic_model_immutability():
    run = _make_test_run("run_immut", evidence_start=100, evidence_end=200, evidence_file_id="ev_01")
    graph = build_evidence_graph_from_runs([run])

    node = graph.nodes[0]
    with pytest.raises(ValidationError):
        node.status = "CORRUPTED"

    cluster = graph.clusters[0]
    with pytest.raises(ValidationError):
        cluster.cluster_start = 999


# ═════════════════════════════════════════════════════════════════════════════
# 31. API Endpoint GET /api/cases/{case_id}/graph
# ═════════════════════════════════════════════════════════════════════════════

def test_31_api_endpoint_get_case_graph():
    from backend.app.store import store

    # Create a real case in the active store
    case = store.create_case("API Graph Test Case")
    run = _make_test_run("run_api_01", case_id=case.case_id, evidence_file_id="ev_api_01")
    store.add_recovery_run(run)

    client = TestClient(app)

    # 1. Successful fetch
    res = client.get(f"/api/cases/{case.case_id}/graph")
    assert res.status_code == 200
    data = res.json()
    assert data["case_id"] == case.case_id
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["evidence_file_id"] == "ev_api_01"

    # 2. Filter by evidence_file_id
    res_filtered = client.get(f"/api/cases/{case.case_id}/graph?evidence_file_id=ev_api_01")
    assert res_filtered.status_code == 200
    assert len(res_filtered.json()["nodes"]) == 1

    res_empty = client.get(f"/api/cases/{case.case_id}/graph?evidence_file_id=other_buf")
    assert res_empty.status_code == 200
    assert len(res_empty.json()["nodes"]) == 0

    # 3. 404 on missing case
    res_404 = client.get("/api/cases/missing_case_123/graph")
    assert res_404.status_code == 404
