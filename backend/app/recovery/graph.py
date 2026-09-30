"""
graph.py — Deterministic Evidence Relationship Graph & Artifact Clustering Engine.

Milestone 3.4: Construct directed, labeled evidence relationship graphs and
connected-component clusters over canonical RecoveryRun forensic execution traces.
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any, Set
from collections import defaultdict

from backend.app.models.recovery_run import RecoveryRun
from backend.app.models.evidence_graph import (
    GraphNode,
    GraphEdge,
    ArtifactCluster,
    EvidenceBufferSummary,
    EvidenceGraphMetadata,
    EvidenceGraph,
)


def resolve_evidence_file_id(run: RecoveryRun) -> Optional[str]:
    """Resolve authoritative evidence file identifier without synthesizing fake IDs.

    Extracts evidence_file_id strictly from run.provenance['evidence_file_id'].
    Accepts it only if it is a non-empty string.
    Otherwise returns None.
    Never synthesizes fallback labels, filenames, hashes, or defaults.
    """
    if run.provenance and isinstance(run.provenance.get("evidence_file_id"), str):
        val = run.provenance["evidence_file_id"].strip()
        if val:
            return val
    return None


class UnionFind:
    """Disjoint-Set Union (DSU) with path compression and union-by-rank."""

    def __init__(self, elements: List[str]) -> None:
        self.parent: Dict[str, str] = {x: x for x in elements}
        self.rank: Dict[str, int] = {x: 0 for x in elements}

    def find(self, x: str) -> str:
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x: str, y: str) -> None:
        root_x = self.find(x)
        root_y = self.find(y)
        if root_x == root_y:
            return
        if self.rank[root_x] < self.rank[root_y]:
            self.parent[root_x] = root_y
        elif self.rank[root_x] > self.rank[root_y]:
            self.parent[root_y] = root_x
        else:
            self.parent[root_y] = root_x
            self.rank[root_x] += 1


def classify_cluster_relationships(edges_in_cluster: List[GraphEdge], node_count: int) -> str:
    """Classify cluster relationships deterministically based on edge families present.

    Options:
    - ISOLATED: 0 internal edges
    - COEXTENSIVE_SET: all internal edges are COEXTENSIVE
    - CONTAINMENT_TREE: all internal edges are CONTAINS or CONTAINED_BY
    - OVERLAP_SPAN: all internal edges are OVERLAPS
    - MIXED: more than one relationship family is present
    """
    if node_count <= 1 or len(edges_in_cluster) == 0:
        return "ISOLATED"

    rel_types = {e.relationship_type for e in edges_in_cluster}
    has_coextensive = "COEXTENSIVE" in rel_types
    has_containment = bool(rel_types & {"CONTAINS", "CONTAINED_BY"})
    has_overlap = "OVERLAPS" in rel_types

    distinct_families = sum([has_coextensive, has_containment, has_overlap])

    if distinct_families > 1:
        return "MIXED"
    elif has_coextensive:
        return "COEXTENSIVE_SET"
    elif has_containment:
        return "CONTAINMENT_TREE"
    elif has_overlap:
        return "OVERLAP_SPAN"
    else:
        return "ISOLATED"


def build_evidence_graph_from_runs(
    runs: List[RecoveryRun],
    case_id: Optional[str] = None,
    candidate_cap_metadata: Optional[Dict[str, Any]] = None,
) -> EvidenceGraph:
    """Build a deterministic EvidenceGraph from a collection of canonical RecoveryRuns.

    Args:
        runs: List of evaluated canonical RecoveryRun traces.
        case_id: Optional case identifier.
        candidate_cap_metadata: Optional dictionary mapping evidence_file_id to cap info,
            or global cap info dictionary with keys ('candidate_cap_enforced',
            'total_discovered_candidates', 'candidates_omitted').

    Returns:
        Immutable EvidenceGraph container.
    """
    if not runs:
        meta = EvidenceGraphMetadata(
            case_id=case_id,
            total_evidence_buffers=0,
            total_nodes=0,
            total_edges=0,
            total_clusters=0,
            candidate_cap_enforced=False,
            total_discovered_candidates=0,
            candidates_omitted=0,
            graph_is_complete=True,
        )
        return EvidenceGraph(
            case_id=case_id,
            evidence_buffers=[],
            nodes=[],
            edges=[],
            clusters=[],
            metadata=meta,
        )

    # 1. Deterministically order runs by run_id
    sorted_runs = sorted(runs, key=lambda r: (r.run_id,))

    # 2. Extract initial node properties
    raw_nodes: List[Dict[str, Any]] = []
    for run in sorted_runs:
        prov = run.provenance or {}
        ev_file_id = resolve_evidence_file_id(run)

        # Physical offsets
        ev_start = int(prov.get("evidence_start", 0))
        ev_end_val = prov.get("evidence_end")
        ev_end = int(ev_end_val) if ev_end_val is not None else None
        coord_sys = str(prov.get("coordinate_system", "physical_evidence_offsets"))

        # Confidence score on locked 0.0–100.0 scale
        if isinstance(run.confidence, dict):
            conf_score = float(run.confidence.get("total", 0.0))
        elif isinstance(run.confidence, (int, float)):
            conf_score = float(run.confidence)
        else:
            conf_score = 0.0

        det_method = str(prov.get("detection_method", "unknown"))

        raw_nodes.append({
            "node_id": f"node_{run.run_id}",
            "candidate_id": run.candidate_id,  # Optional[str], never synthesized
            "run_id": run.run_id,
            "artifact_id": run.artifact_id,
            "evidence_file_id": ev_file_id,
            "format": run.format,
            "evidence_start": ev_start,
            "evidence_end": ev_end,
            "coordinate_system": coord_sys,
            "status": run.status,
            "confidence_score": conf_score,
            "verified_bytes": int(run.total_verified_bytes),
            "reconstructed_bytes": int(run.total_reconstructed_bytes),
            "missing_bytes": int(run.total_missing_bytes),
            "detection_method": det_method,
            "is_ambiguous": False,  # Computed below
        })

    # 3. Group nodes by coordinate scope (evidence_file_id)
    # None represents unknown coordinate scope (isolated from all spatial comparisons)
    scoped_nodes: Dict[Optional[str], List[Dict[str, Any]]] = defaultdict(list)
    for n in raw_nodes:
        scoped_nodes[n["evidence_file_id"]].append(n)

    # 4. Pairwise spatial relationship evaluation (strictly intra-buffer for non-None scopes)
    all_edges: List[GraphEdge] = []
    # Track outgoing edges per node for ambiguity evaluation
    node_outgoing_edges: Dict[str, List[GraphEdge]] = defaultdict(list)
    node_by_id: Dict[str, Dict[str, Any]] = {n["node_id"]: n for n in raw_nodes}

    for ev_id, nodes in scoped_nodes.items():
        if ev_id is None:
            # Unknown coordinate scope: strictly ZERO spatial edges
            continue

        n_count = len(nodes)
        for i in range(n_count):
            for j in range(i + 1, n_count):
                a = nodes[i]
                b = nodes[j]

                # Guard: Both nodes must have bounded evidence_end
                if a["evidence_end"] is None or b["evidence_end"] is None:
                    continue

                a_s, a_e = a["evidence_start"], a["evidence_end"]
                b_s, b_e = b["evidence_start"], b["evidence_end"]

                # Guard: Touching boundaries (a_e == b_s or b_e == a_s) are disjoint
                if a_e <= b_s or b_e <= a_s:
                    continue

                # I. COEXTENSIVE: identical physical bounds
                if a_s == b_s and a_e == b_e:
                    ov_len = a_e - a_s
                    edge_ab = GraphEdge(
                        edge_id=f"edge_{a['node_id']}_{b['node_id']}_COEXTENSIVE",
                        source_node_id=a["node_id"],
                        target_node_id=b["node_id"],
                        relationship_type="COEXTENSIVE",
                        evidence_file_id=ev_id,
                        evidence_basis="interval_coextensive",
                        overlap_start=a_s,
                        overlap_end=a_e,
                        overlap_bytes=ov_len,
                    )
                    edge_ba = GraphEdge(
                        edge_id=f"edge_{b['node_id']}_{a['node_id']}_COEXTENSIVE",
                        source_node_id=b["node_id"],
                        target_node_id=a["node_id"],
                        relationship_type="COEXTENSIVE",
                        evidence_file_id=ev_id,
                        evidence_basis="interval_coextensive",
                        overlap_start=a_s,
                        overlap_end=a_e,
                        overlap_bytes=ov_len,
                    )
                    all_edges.extend([edge_ab, edge_ba])
                    node_outgoing_edges[a["node_id"]].append(edge_ab)
                    node_outgoing_edges[b["node_id"]].append(edge_ba)

                # II. CONTAINS / CONTAINED_BY: strict enclosure
                elif (a_s <= b_s and a_e > b_e) or (a_s < b_s and a_e >= b_e):
                    # a strictly contains b
                    ov_len = b_e - b_s
                    edge_ab = GraphEdge(
                        edge_id=f"edge_{a['node_id']}_{b['node_id']}_CONTAINS",
                        source_node_id=a["node_id"],
                        target_node_id=b["node_id"],
                        relationship_type="CONTAINS",
                        evidence_file_id=ev_id,
                        evidence_basis="interval_containment",
                        overlap_start=b_s,
                        overlap_end=b_e,
                        overlap_bytes=ov_len,
                    )
                    edge_ba = GraphEdge(
                        edge_id=f"edge_{b['node_id']}_{a['node_id']}_CONTAINED_BY",
                        source_node_id=b["node_id"],
                        target_node_id=a["node_id"],
                        relationship_type="CONTAINED_BY",
                        evidence_file_id=ev_id,
                        evidence_basis="interval_containment",
                        overlap_start=b_s,
                        overlap_end=b_e,
                        overlap_bytes=ov_len,
                    )
                    all_edges.extend([edge_ab, edge_ba])
                    node_outgoing_edges[a["node_id"]].append(edge_ab)
                    node_outgoing_edges[b["node_id"]].append(edge_ba)

                elif (b_s <= a_s and b_e > a_e) or (b_s < a_s and b_e >= a_e):
                    # b strictly contains a
                    ov_len = a_e - a_s
                    edge_ba = GraphEdge(
                        edge_id=f"edge_{b['node_id']}_{a['node_id']}_CONTAINS",
                        source_node_id=b["node_id"],
                        target_node_id=a["node_id"],
                        relationship_type="CONTAINS",
                        evidence_file_id=ev_id,
                        evidence_basis="interval_containment",
                        overlap_start=a_s,
                        overlap_end=a_e,
                        overlap_bytes=ov_len,
                    )
                    edge_ab = GraphEdge(
                        edge_id=f"edge_{a['node_id']}_{b['node_id']}_CONTAINED_BY",
                        source_node_id=a["node_id"],
                        target_node_id=b["node_id"],
                        relationship_type="CONTAINED_BY",
                        evidence_file_id=ev_id,
                        evidence_basis="interval_containment",
                        overlap_start=a_s,
                        overlap_end=a_e,
                        overlap_bytes=ov_len,
                    )
                    all_edges.extend([edge_ba, edge_ab])
                    node_outgoing_edges[b["node_id"]].append(edge_ba)
                    node_outgoing_edges[a["node_id"]].append(edge_ab)

                # III. OVERLAPS: partial overlap without containment
                elif max(a_s, b_s) < min(a_e, b_e):
                    ov_s = max(a_s, b_s)
                    ov_e = min(a_e, b_e)
                    ov_len = ov_e - ov_s
                    edge_ab = GraphEdge(
                        edge_id=f"edge_{a['node_id']}_{b['node_id']}_OVERLAPS",
                        source_node_id=a["node_id"],
                        target_node_id=b["node_id"],
                        relationship_type="OVERLAPS",
                        evidence_file_id=ev_id,
                        evidence_basis="interval_overlap",
                        overlap_start=ov_s,
                        overlap_end=ov_e,
                        overlap_bytes=ov_len,
                    )
                    edge_ba = GraphEdge(
                        edge_id=f"edge_{b['node_id']}_{a['node_id']}_OVERLAPS",
                        source_node_id=b["node_id"],
                        target_node_id=a["node_id"],
                        relationship_type="OVERLAPS",
                        evidence_file_id=ev_id,
                        evidence_basis="interval_overlap",
                        overlap_start=ov_s,
                        overlap_end=ov_e,
                        overlap_bytes=ov_len,
                    )
                    all_edges.extend([edge_ab, edge_ba])
                    node_outgoing_edges[a["node_id"]].append(edge_ab)
                    node_outgoing_edges[b["node_id"]].append(edge_ba)

    # Sort all edges deterministically
    all_edges.sort(key=lambda e: (e.evidence_file_id, e.source_node_id, e.target_node_id, e.relationship_type))

    # 5. Evaluate node ambiguity (Rule 9)
    # A node is ambiguous iff it has a COEXTENSIVE edge to a node with a different format,
    # OR it has an OVERLAPS edge.
    for n in raw_nodes:
        nid = n["node_id"]
        is_ambig = False
        for edge in node_outgoing_edges.get(nid, []):
            if edge.relationship_type == "OVERLAPS":
                is_ambig = True
                break
            elif edge.relationship_type == "COEXTENSIVE":
                target_node = node_by_id.get(edge.target_node_id)
                if target_node and target_node["format"] != n["format"]:
                    is_ambig = True
                    break
        n["is_ambiguous"] = is_ambig

    # Construct immutable GraphNode models
    final_nodes = [GraphNode(**n) for n in raw_nodes]
    final_node_by_id = {n.node_id: n for n in final_nodes}

    # 6. Connected component clustering (Rule 7 & 8)
    all_clusters: List[ArtifactCluster] = []

    # 6a. Process unknown-scope nodes (evidence_file_id is None)
    # Each unknown-scope node gets its own isolated singleton cluster
    unscoped_nodes = scoped_nodes.get(None, [])
    for idx, un in enumerate(unscoped_nodes):
        nid = un["node_id"]
        node_obj = final_node_by_id[nid]
        c = ArtifactCluster(
            cluster_id=f"cluster_unscoped_{node_obj.evidence_start}_{idx}",
            evidence_file_id=None,
            cluster_start=node_obj.evidence_start,
            cluster_end=node_obj.evidence_end,  # None if None, never cluster_start
            node_ids=[nid],
            formats=[node_obj.format],
            relationship_classification="ISOLATED",
            has_ambiguity=node_obj.is_ambiguous,
            total_nodes=1,
        )
        all_clusters.append(c)

    # 6b. Process scoped nodes per evidence_file_id
    edge_set_by_pair: Dict[frozenset[str], List[GraphEdge]] = defaultdict(list)
    for edge in all_edges:
        edge_set_by_pair[frozenset([edge.source_node_id, edge.target_node_id])].append(edge)

    for ev_id, nodes in scoped_nodes.items():
        if ev_id is None or not nodes:
            continue

        node_id_list = [n["node_id"] for n in nodes]
        uf = UnionFind(node_id_list)

        # Union along edges in this buffer
        buf_edges = [e for e in all_edges if e.evidence_file_id == ev_id]
        for edge in buf_edges:
            uf.union(edge.source_node_id, edge.target_node_id)

        # Group by component root
        components: Dict[str, List[str]] = defaultdict(list)
        for nid in node_id_list:
            root = uf.find(nid)
            components[root].append(nid)

        # Build clusters for this buffer
        # Deterministically sort components by minimum evidence_start, then node_id
        comp_list = []
        for root, member_ids in components.items():
            member_nodes = [final_node_by_id[mid] for mid in sorted(member_ids)]
            min_start = min(m.evidence_start for m in member_nodes)
            comp_list.append((min_start, member_nodes[0].node_id, member_nodes))

        comp_list.sort(key=lambda item: (item[0], item[1]))

        for c_idx, (min_start, _, member_nodes) in enumerate(comp_list):
            m_ids = [m.node_id for m in member_nodes]
            m_formats = sorted(list(set(m.format for m in member_nodes)))

            # Spatial extents
            bounded_ends = [m.evidence_end for m in member_nodes if m.evidence_end is not None]
            c_end = max(bounded_ends) if bounded_ends else None  # None if no bounded member, NEVER cluster_start

            # Collect internal edges
            m_id_set = set(m_ids)
            internal_edges = [
                e for e in buf_edges
                if e.source_node_id in m_id_set and e.target_node_id in m_id_set
            ]

            rel_class = classify_cluster_relationships(internal_edges, len(member_nodes))
            has_ambig = any(m.is_ambiguous for m in member_nodes)

            cluster = ArtifactCluster(
                cluster_id=f"cluster_{ev_id}_{min_start}_{c_idx}",
                evidence_file_id=ev_id,
                cluster_start=min_start,
                cluster_end=c_end,
                node_ids=m_ids,
                formats=m_formats,
                relationship_classification=rel_class,
                has_ambiguity=has_ambig,
                total_nodes=len(member_nodes),
            )
            all_clusters.append(cluster)

    # Sort all clusters deterministically
    all_clusters.sort(key=lambda c: (c.evidence_file_id or "", c.cluster_start, c.cluster_id))

    # 7. Evidence Buffer Summaries (Rule 10)
    evidence_buffers: List[EvidenceBufferSummary] = []
    distinct_ev_ids = sorted([ev_id for ev_id in scoped_nodes.keys() if ev_id is not None])

    for ev_id in distinct_ev_ids:
        b_nodes = [n for n in final_nodes if n.evidence_file_id == ev_id]
        b_edges = [e for e in all_edges if e.evidence_file_id == ev_id]
        b_clusters = [c for c in all_clusters if c.evidence_file_id == ev_id]

        bounded_c = [c for c in b_clusters if c.cluster_end is not None]
        if bounded_c:
            byte_span = max(c.cluster_end for c in bounded_c) - min(c.cluster_start for c in bounded_c)
        else:
            byte_span = None

        # Resolve candidate cap metadata for this buffer
        cap_enforced = False
        disc_count = len(b_nodes)
        omitted_count = 0

        if candidate_cap_metadata:
            # Check if keyed by ev_id or flat dict
            if ev_id in candidate_cap_metadata and isinstance(candidate_cap_metadata[ev_id], dict):
                buf_meta = candidate_cap_metadata[ev_id]
                cap_enforced = bool(buf_meta.get("candidate_cap_enforced", False))
                disc_count = int(buf_meta.get("total_discovered_candidates", len(b_nodes)))
                omitted_count = int(buf_meta.get("candidates_omitted", 0))
            elif "candidate_cap_enforced" in candidate_cap_metadata:
                cap_enforced = bool(candidate_cap_metadata.get("candidate_cap_enforced", False))
                disc_count = int(candidate_cap_metadata.get("total_discovered_candidates", len(b_nodes)))
                omitted_count = int(candidate_cap_metadata.get("candidates_omitted", 0))

        summary = EvidenceBufferSummary(
            evidence_file_id=ev_id,
            total_nodes=len(b_nodes),
            total_edges=len(b_edges),
            total_clusters=len(b_clusters),
            total_byte_span=byte_span,
            candidate_cap_enforced=cap_enforced,
            total_discovered_candidates=disc_count,
            candidates_omitted=omitted_count,
            buffer_is_complete=not cap_enforced,
        )
        evidence_buffers.append(summary)

    # 8. Graph-level metadata with aggregated cap statistics
    if evidence_buffers:
        agg_cap_enforced = any(b.candidate_cap_enforced for b in evidence_buffers)
        agg_discovered = sum(b.total_discovered_candidates for b in evidence_buffers)
        agg_omitted = sum(b.candidates_omitted for b in evidence_buffers)
        agg_complete = all(b.buffer_is_complete for b in evidence_buffers)
    else:
        agg_cap_enforced = False
        agg_discovered = len(final_nodes)
        agg_omitted = 0
        agg_complete = True

    metadata = EvidenceGraphMetadata(
        case_id=case_id,
        total_evidence_buffers=len(evidence_buffers),
        total_nodes=len(final_nodes),
        total_edges=len(all_edges),
        total_clusters=len(all_clusters),
        candidate_cap_enforced=agg_cap_enforced,
        total_discovered_candidates=agg_discovered,
        candidates_omitted=agg_omitted,
        graph_is_complete=agg_complete,
    )

    return EvidenceGraph(
        case_id=case_id,
        evidence_buffers=evidence_buffers,
        nodes=final_nodes,
        edges=all_edges,
        clusters=all_clusters,
        metadata=metadata,
    )


def build_case_evidence_graph(
    case_id: str,
    store: Any,
    evidence_file_id: Optional[str] = None,
) -> EvidenceGraph:
    """Build evidence relationship graph for a case from its persisted recovery runs.

    Args:
        case_id: The case identifier.
        store: SQLite or repository store implementing CaseRepository and RecoveryRunRepository.
        evidence_file_id: Optional filter to restrict graph to a specific evidence buffer.

    Returns:
        Immutable EvidenceGraph.
    """
    case = store.get_case(case_id)
    if case is None:
        raise KeyError(f"Case '{case_id}' not found")

    artifacts = store.get_case_artifacts(case_id) or []
    runs: List[RecoveryRun] = []
    seen_run_ids: Set[str] = set()

    for art in artifacts:
        run = None
        if hasattr(store, "get_recovery_run_by_artifact"):
            run = store.get_recovery_run_by_artifact(art.artifact_id)
        if run is None and art.run_id and hasattr(store, "get_recovery_run"):
            run = store.get_recovery_run(art.run_id)

        if run is not None and run.run_id not in seen_run_ids:
            seen_run_ids.add(run.run_id)
            runs.append(run)

    # Also check if store has direct runs matching case_id
    if hasattr(store, "list_recovery_runs"):
        all_runs = store.list_recovery_runs()
        for r in all_runs:
            r_case_id = None
            if r.provenance and isinstance(r.provenance, dict):
                r_case_id = r.provenance.get("case_id")
            if getattr(r, "case_id", None) == case_id or r_case_id == case_id:
                if r.run_id not in seen_run_ids:
                    seen_run_ids.add(r.run_id)
                    runs.append(r)

    # Filter by evidence_file_id if requested
    if evidence_file_id is not None:
        runs = [r for r in runs if resolve_evidence_file_id(r) == evidence_file_id]

    return build_evidence_graph_from_runs(runs=runs, case_id=case_id)
