"""
test_sqlite_repositories_m32.py — Test Suite for Milestone 3.2.2 SQLite Repositories.

Verifies:
A. CaseRepository (create, invalid name, get, list, dynamic count, evidence, chunks, size checks)
B. ArtifactRepository (case artifacts, missing case, standalone, get, get_case_artifacts semantics,
   bytes, AI summary update, Pipeline B store/metadata/bytes)
C. RecoveryRunRepository (simple run, complex nested run, list ordering, authoritative linkage, fallback)
D. Persistence & Process Restart (full multi-entity persistence across database close/reopen)
E. Transaction Rollback (evidence failure isolation, artifact failure isolation)
F. Foreign Keys & Clear Safety (clear_all_tables order, PRAGMA foreign_key_check)
"""

from __future__ import annotations

import os
import sqlite3
import pytest
from datetime import datetime, timezone

from backend.app.ingestion import compute_metadata
from backend.app.models.artifact import (
    ArtifactRecord,
    ArtifactResponse,
    ConfidenceBreakdownSchema,
    ArtifactProvenanceSchema,
)
from backend.app.models.case import CaseResponse, EvidenceMetadata
from backend.app.models.recovery_run import (
    DamageRegion,
    Fragment,
    FragmentRelationship,
    PipelineEvent,
    ReconstructionStep,
    RecoveryRun,
)
from backend.app.storage.contracts import (
    ArtifactRepository,
    CaseRepository,
    RecoveryRunRepository,
)
from backend.app.storage.memory_store import MAX_EVIDENCE_SIZE
from backend.app.storage.sqlite_engine import SqliteEngine
from backend.app.storage.sqlite_store import SqliteStore


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def mem_engine() -> SqliteEngine:
    """Provide an in-memory SqliteEngine."""
    engine = SqliteEngine(":memory:")
    engine.initialize()
    yield engine
    engine.close()


@pytest.fixture
def mem_store(mem_engine) -> SqliteStore:
    """Provide a SqliteStore backed by an in-memory engine."""
    return SqliteStore(mem_engine)


@pytest.fixture
def file_engine(tmp_path) -> SqliteEngine:
    """Provide a file-backed SqliteEngine."""
    db_path = str(tmp_path / "sqlite_store_test.db")
    engine = SqliteEngine(db_path)
    engine.initialize()
    yield engine
    engine.close()


@pytest.fixture
def file_store(file_engine) -> SqliteStore:
    """Provide a SqliteStore backed by a file engine."""
    return SqliteStore(file_engine)


# ── Group A: CaseRepository Tests ─────────────────────────────────────────────

def test_a_create_case(mem_store):
    """Case creation returns CaseResponse with generated ID, created_at, and zero counts."""
    case = mem_store.create_case("Forensic Incident Alpha", "Investigation description")
    assert isinstance(case, CaseResponse)
    assert case.case_id.startswith("case_")
    assert case.name == "Forensic Incident Alpha"
    assert case.description == "Investigation description"
    assert case.evidence is None
    assert case.artifact_count == 0
    assert case.created_at is not None


def test_a_create_case_invalid_name(mem_store):
    """Empty or whitespace-only case names raise ValueError."""
    with pytest.raises(ValueError, match="Case name cannot be empty or invalid string"):
        mem_store.create_case("")
    with pytest.raises(ValueError, match="Case name cannot be empty or invalid string"):
        mem_store.create_case("   \t\n  ")
    with pytest.raises(ValueError, match="Case name cannot be empty or invalid string"):
        mem_store.create_case(None)  # type: ignore


def test_a_get_case(mem_store):
    """Get case returns CaseResponse when present, None when missing."""
    assert mem_store.get_case("case_missing") is None

    case = mem_store.create_case("Case Beta")
    retrieved = mem_store.get_case(case.case_id)
    assert retrieved is not None
    assert retrieved.case_id == case.case_id
    assert retrieved.name == "Case Beta"
    assert retrieved.artifact_count == 0


def test_a_list_cases(mem_store):
    """List cases returns [] when empty, preserves insertion order, and dynamically reports counts."""
    assert mem_store.list_cases() == []

    c1 = mem_store.create_case("Case 1")
    c2 = mem_store.create_case("Case 2")
    c3 = mem_store.create_case("Case 3")

    cases = mem_store.list_cases()
    assert len(cases) == 3
    assert [c.case_id for c in cases] == [c1.case_id, c2.case_id, c3.case_id]


def test_a_add_evidence(mem_store):
    """Add evidence stores metadata, raw bytes, and chunks atomically."""
    case = mem_store.create_case("Evidence Case")
    payload = b"HEADER_RECORD_DATA_1234567890_FOOTER"

    meta = mem_store.add_evidence(case.case_id, "evidence.img", payload)
    assert isinstance(meta, EvidenceMetadata)
    assert meta.filename == "evidence.img"
    assert meta.file_size == len(payload)
    assert meta.sha256 == compute_metadata(payload, "evidence.img").sha256

    # Verify updated case has evidence and artifact_count remains 0
    updated_case = mem_store.get_case(case.case_id)
    assert updated_case is not None
    assert updated_case.evidence is not None
    assert updated_case.evidence.sha256 == meta.sha256
    assert updated_case.artifact_count == 0

    # Verify raw bytes retrieval
    raw = mem_store.get_evidence_bytes(case.case_id)
    assert raw == payload

    # Verify chunk retrieval
    chunks = mem_store.get_evidence_chunks(case.case_id)
    assert chunks is not None
    assert len(chunks) >= 1
    assert chunks[0].index == 0
    assert chunks[0].data == payload
    assert chunks[0].length == len(payload)


def test_a_add_evidence_validation_errors(mem_store):
    """Add evidence enforces missing case KeyError, EMPTY_FILE, and FILE_TOO_LARGE."""
    # Missing case
    with pytest.raises(KeyError, match="Case 'case_missing' not found"):
        mem_store.add_evidence("case_missing", "ev.img", b"some bytes")

    case = mem_store.create_case("Size Test Case")

    # Empty file
    with pytest.raises(ValueError, match="EMPTY_FILE"):
        mem_store.add_evidence(case.case_id, "ev.img", b"")

    # Oversized file (> 5 MiB)
    oversized = b"X" * (MAX_EVIDENCE_SIZE + 1)
    with pytest.raises(ValueError, match="FILE_TOO_LARGE"):
        mem_store.add_evidence(case.case_id, "ev.img", oversized)


def test_a_get_evidence_chunks_missing(mem_store):
    """get_evidence_chunks returns None for missing case or case without evidence."""
    assert mem_store.get_evidence_chunks("case_missing") is None

    case = mem_store.create_case("No Evidence Case")
    assert mem_store.get_evidence_chunks(case.case_id) is None
    assert mem_store.get_evidence_bytes(case.case_id) is None


# ── Group B: ArtifactRepository Tests ─────────────────────────────────────────

def test_b_add_artifact_and_dynamic_count(mem_store):
    """Adding an artifact increments the case artifact count and enables retrieval."""
    case = mem_store.create_case("Artifact Test Case")
    assert case.artifact_count == 0

    art_response = ArtifactResponse(
        artifact_id="art_001",
        case_id=case.case_id,
        format="png",
        size_bytes=1000,
        confidence_score=95,
        score_breakdown=ConfidenceBreakdownSchema(
            header_validity=100,
            footer_validity=100,
            structural_validation=90,
            size_plausibility=90,
            reconstruction_integrity=95,
            total=95,
        ),
        status="FULLY_RECOVERED",
        provenance=ArtifactProvenanceSchema(
            verified_bytes=1000,
            reconstructed_bytes=0,
            missing_bytes=0,
            reconstruction_method="NONE",
            validation_status="PASSED",
        ),
        content_preview="PNG_PREVIEW",
        metadata={"run_id": "run_001"},
    )

    added = mem_store.add_artifact(art_response)
    assert added.artifact_id == "art_001"

    # Case artifact count must now be 1
    updated_case = mem_store.get_case(case.case_id)
    assert updated_case.artifact_count == 1

    # In list_cases as well
    cases = mem_store.list_cases()
    assert cases[0].artifact_count == 1

    # Retrieve artifact
    retrieved = mem_store.get_artifact("art_001")
    assert retrieved is not None
    assert retrieved.artifact_id == "art_001"
    assert retrieved.confidence_score == 95
    assert retrieved.provenance.verified_bytes == 1000


def test_b_add_artifact_missing_case(mem_store):
    """Adding an artifact for a non-existent case raises KeyError."""
    art = ArtifactResponse(
        artifact_id="art_orphan",
        case_id="case_non_existent",
        format="txt",
        size_bytes=10,
        confidence_score=50,
        score_breakdown=ConfidenceBreakdownSchema(
            header_validity=50, footer_validity=50, structural_validation=50,
            size_plausibility=50, reconstruction_integrity=50, total=50,
        ),
        status="PARTIAL",
        provenance=ArtifactProvenanceSchema(
            verified_bytes=10, reconstructed_bytes=0, missing_bytes=0,
            reconstruction_method="NONE", validation_status="PASSED",
        ),
    )
    with pytest.raises(KeyError, match="Case 'case_non_existent' not found"):
        mem_store.add_artifact(art)


def test_b_save_standalone_artifact_record(mem_store):
    """save_artifact_record supports case_id=None for Pipeline B standalone recoveries."""
    record = ArtifactRecord(
        artifact_id="standalone_art_001",
        case_id=None,
        run_id="run_standalone_1",
        original_filename="upload.bin",
        recovered_filename="recovered_upload.bin",
        format="bin",
        status="FULLY_RECOVERED",
        confidence_score=98.5,
        verified_bytes=500,
        reconstructed_bytes=0,
        missing_bytes=0,
        total_input_bytes=500,
    )
    saved = mem_store.save_artifact_record(record)
    assert saved.artifact_id == "standalone_art_001"

    retrieved = mem_store.get_artifact_record("standalone_art_001")
    assert retrieved is not None
    assert retrieved.case_id is None
    assert retrieved.run_id == "run_standalone_1"
    assert retrieved.confidence_score == 98.5


def test_b_get_case_artifacts_semantics(mem_store):
    """get_case_artifacts returns None for missing case, [] for empty case, list for populated."""
    # 1. Non-existent case returns None (CRITICAL for API 404 response)
    assert mem_store.get_case_artifacts("case_missing") is None

    # 2. Existing case with zero artifacts returns []
    case = mem_store.create_case("Empty Artifacts Case")
    assert mem_store.get_case_artifacts(case.case_id) == []

    # 3. Populated case returns list in registration order
    art1 = ArtifactResponse(
        artifact_id="art_seq_1", case_id=case.case_id, format="txt", size_bytes=10, confidence_score=80,
        score_breakdown=ConfidenceBreakdownSchema(header_validity=80, footer_validity=80, structural_validation=80, size_plausibility=80, reconstruction_integrity=80, total=80),
        status="FULLY_RECOVERED",
        provenance=ArtifactProvenanceSchema(verified_bytes=10, reconstructed_bytes=0, missing_bytes=0, reconstruction_method="NONE", validation_status="PASSED"),
    )
    art2 = ArtifactResponse(
        artifact_id="art_seq_2", case_id=case.case_id, format="csv", size_bytes=20, confidence_score=90,
        score_breakdown=ConfidenceBreakdownSchema(header_validity=90, footer_validity=90, structural_validation=90, size_plausibility=90, reconstruction_integrity=90, total=90),
        status="FULLY_RECOVERED",
        provenance=ArtifactProvenanceSchema(verified_bytes=20, reconstructed_bytes=0, missing_bytes=0, reconstruction_method="NONE", validation_status="PASSED"),
    )
    mem_store.add_artifact(art1)
    mem_store.add_artifact(art2)

    retrieved_list = mem_store.get_case_artifacts(case.case_id)
    assert retrieved_list is not None
    assert len(retrieved_list) == 2
    assert [a.artifact_id for a in retrieved_list] == ["art_seq_1", "art_seq_2"]


def test_b_artifact_bytes_and_ai_summary(mem_store):
    """Artifact raw bytes and AI summary update round-trip correctly."""
    case = mem_store.create_case("Blob/Summary Case")
    art = ArtifactResponse(
        artifact_id="art_summary_test", case_id=case.case_id, format="txt", size_bytes=20, confidence_score=75,
        score_breakdown=ConfidenceBreakdownSchema(header_validity=75, footer_validity=75, structural_validation=75, size_plausibility=75, reconstruction_integrity=75, total=75),
        status="PARTIAL",
        provenance=ArtifactProvenanceSchema(verified_bytes=20, reconstructed_bytes=0, missing_bytes=0, reconstruction_method="NONE", validation_status="PASSED"),
    )
    mem_store.add_artifact(art)

    payload = b"RECOVERED_PLAINTEXT_PAYLOAD"
    mem_store.store_artifact_bytes("art_summary_test", payload)
    assert mem_store.get_artifact_bytes("art_summary_test") == payload

    # Update AI summary
    mem_store.update_artifact_ai_summary("art_summary_test", '{"summary": "Forensic reconstruction successful"}')
    retrieved = mem_store.get_artifact_record("art_summary_test")
    assert retrieved is not None
    assert retrieved.ai_summary == '{"summary": "Forensic reconstruction successful"}'


def test_b_pipeline_b_harmonized_methods(mem_store):
    """Pipeline B harmonized methods store metadata, bytes, and linkage atomically."""
    file_id = "rec_file_alpha"
    payload = b"PIPELINE_B_RAW_BYTES"
    meta_dict = {
        "file_id": file_id,
        "run_id": "run_p_b",
        "original_filename": "corrupted.jpg",
        "recovered_filename": "recovered_corrupted.jpg",
        "format": "jpeg",
        "status": "FULLY_RECOVERED",
        "confidence_score": 92.0,
        "verified_bytes": len(payload),
        "reconstructed_bytes": 0,
        "missing_bytes": 0,
        "reconstruction_method": "NONE",
        "validation_status": "PASSED",
        "is_downloadable": True,
        "download_url": f"/api/recover-file/{file_id}/download",
        "content_preview": "JPEG_PREVIEW",
        "score_breakdown": {"header_validity": 100.0, "total": 92.0},
        "validation_details": {"exif": True},
        "fragments": [{"fragment_id": "frag_1", "offset": 0, "length": len(payload)}],
        "damage_regions": [],
        "reconstruction_steps": [],
        "total_input_bytes": len(payload),
    }

    res = mem_store.store_recovered_file(file_id, meta_dict, payload)
    assert res["file_id"] == file_id

    # Retrieve metadata dict
    retrieved_meta = mem_store.get_recovered_file_metadata(file_id)
    assert retrieved_meta is not None
    assert retrieved_meta["file_id"] == file_id
    assert retrieved_meta["format"] == "jpeg"
    assert retrieved_meta["confidence_score"] == 92.0
    assert len(retrieved_meta["fragments"]) == 1

    # Retrieve raw bytes
    retrieved_bytes = mem_store.get_recovered_file_bytes(file_id)
    assert retrieved_bytes == payload


# ── Group C: RecoveryRunRepository Tests ──────────────────────────────────────

def test_c_recovery_run_complex_nested_roundtrip(mem_store):
    """RecoveryRun with deeply nested Fragments, Relationships, DamageRegions, Steps, and Events round-trips."""
    run_id = "run_complex_999"
    now = datetime.now(timezone.utc)

    run = RecoveryRun(
        run_id=run_id,
        artifact_id="art_candidate_1",
        candidate_id="cand_001",
        filename="evidence.pdf",
        format="pdf",
        status="PARTIALLY_RECOVERED",
        detection_mode="known_file",
        started_at=now,
        completed_at=now,
        total_input_bytes=5000,
        total_verified_bytes=4000,
        total_reconstructed_bytes=500,
        total_missing_bytes=500,
        fragments=[
            Fragment(
                fragment_id="frag_head",
                offset=0,
                length=2000,
                end_offset=2000,
                status="VERIFIED",
                source="magic_bytes",
                format="pdf",
                verified_bytes=2000,
                reconstructed_bytes=0,
                missing_bytes=0,
                validation_status="PASSED",
                relationships=[
                    FragmentRelationship(
                        source_fragment_id="frag_head",
                        target_fragment_id="frag_tail",
                        relationship_type="PRECEDES",
                        details={"xref_offset": 1900},
                    )
                ],
            ),
            Fragment(
                fragment_id="frag_tail",
                offset=2500,
                length=2500,
                end_offset=5000,
                status="RECONSTRUCTED",
                source="carved",
                format="pdf",
                verified_bytes=2000,
                reconstructed_bytes=500,
                missing_bytes=0,
                validation_status="PASSED",
                relationships=[],
            ),
        ],
        damage_regions=[
            DamageRegion(
                region_id="dmg_1",
                start_offset=2000,
                end_offset=2500,
                length=500,
                type="MISSING",
                status="RECONSTRUCTED",
                affected_fragment_ids=["frag_head", "frag_tail"],
            )
        ],
        reconstruction_steps=[
            ReconstructionStep(
                step_id="step_1",
                method="BIFRAGMENT_GAP",
                input_fragment_ids=["frag_head", "frag_tail"],
                gap_start=2000,
                gap_end=2500,
                gap_size=500,
                result="SUCCESS",
                verified_bytes=4000,
                reconstructed_bytes=500,
                missing_bytes=0,
                validation_status="PASSED",
                confidence=85.0,
            )
        ],
        events=[
            PipelineEvent(
                event_id="evt_1",
                run_id=run_id,
                sequence=1,
                event_type="SIGNATURE_FOUND",
                timestamp=now,
                message="PDF header detected at offset 0",
                relevant_fragment_ids=["frag_head"],
            )
        ],
        validation={"pdf_xref_valid": True, "object_count": 12},
        confidence={"header_validity": 100, "total": 85.0},
        provenance={"detection_mode": "known_file", "analyzer": "v2_tracer"},
        output={"recovered_bytes": "255044462d312e340a"},
    )

    mem_store.add_recovery_run(run)

    retrieved = mem_store.get_recovery_run(run_id)
    assert retrieved is not None
    assert retrieved.run_id == run_id
    assert retrieved.format == "pdf"
    assert retrieved.status == "PARTIALLY_RECOVERED"
    assert retrieved.started_at == now
    assert len(retrieved.fragments) == 2
    assert retrieved.fragments[0].relationships[0].relationship_type == "PRECEDES"
    assert retrieved.fragments[0].relationships[0].details == {"xref_offset": 1900}
    assert len(retrieved.damage_regions) == 1
    assert retrieved.damage_regions[0].affected_fragment_ids == ["frag_head", "frag_tail"]
    assert len(retrieved.reconstruction_steps) == 1
    assert retrieved.reconstruction_steps[0].method == "BIFRAGMENT_GAP"
    assert len(retrieved.events) == 1
    assert retrieved.events[0].message == "PDF header detected at offset 0"
    assert retrieved.output == {"recovered_bytes": "255044462d312e340a"}


def test_c_list_recovery_runs(mem_store):
    """list_recovery_runs returns runs in insertion order."""
    now = datetime.now(timezone.utc)
    r1 = RecoveryRun(
        run_id="run_1", filename="f1.txt", format="txt", status="FULLY_RECOVERED",
        started_at=now, total_input_bytes=100, total_verified_bytes=100,
        total_reconstructed_bytes=0, total_missing_bytes=0,
    )
    r2 = RecoveryRun(
        run_id="run_2", filename="f2.csv", format="csv", status="FULLY_RECOVERED",
        started_at=now, total_input_bytes=200, total_verified_bytes=200,
        total_reconstructed_bytes=0, total_missing_bytes=0,
    )
    mem_store.add_recovery_run(r1)
    mem_store.add_recovery_run(r2)

    runs = mem_store.list_recovery_runs()
    assert len(runs) == 2
    assert [r.run_id for r in runs] == ["run_1", "run_2"]


def test_c_authoritative_linkage_and_fallback(mem_store):
    """Linkage resolves through artifact_runs first, then metadata fallback."""
    now = datetime.now(timezone.utc)
    run = RecoveryRun(
        run_id="run_target", filename="data.txt", format="txt", status="FULLY_RECOVERED",
        started_at=now, total_input_bytes=50, total_verified_bytes=50,
        total_reconstructed_bytes=0, total_missing_bytes=0,
    )
    mem_store.add_recovery_run(run)

    # 1. Authoritative link via link_artifact_to_run
    mem_store.link_artifact_to_run("art_authoritative", "run_target")
    found_run = mem_store.get_recovery_run_by_artifact("art_authoritative")
    assert found_run is not None
    assert found_run.run_id == "run_target"

    # 2. Fallback via artifact record metadata["run_id"] when not explicitly in artifact_runs
    fallback_rec = ArtifactRecord(
        artifact_id="art_fallback",
        case_id=None,
        run_id=None,  # No direct run_id
        format="txt",
        status="FULLY_RECOVERED",
        confidence_score=90.0,
        metadata={"run_id": "run_target"},
    )
    mem_store.save_artifact_record(fallback_rec)

    # Remove direct artifact_runs row to test metadata fallback specifically
    with mem_store._engine.transaction() as cursor:
        cursor.execute("DELETE FROM artifact_runs WHERE artifact_id = 'art_fallback';")

    fallback_run = mem_store.get_recovery_run_by_artifact("art_fallback")
    assert fallback_run is not None
    assert fallback_run.run_id == "run_target"

    # Missing artifact returns None
    assert mem_store.get_recovery_run_by_artifact("non_existent_art") is None


# ── Group D: Persistence & Process Restart Test ──────────────────────────────

def test_d_process_restart_persistence(tmp_path):
    """Complete data hierarchy survives engine close and process/session restart."""
    db_file = str(tmp_path / "restart_test.db")
    now = datetime.now(timezone.utc)

    # ── Session 1: Populate all storage entities ───────────────────────────
    engine1 = SqliteEngine(db_file)
    store1 = SqliteStore(engine1)

    case = store1.create_case("Restart Case", "Description for restart")
    evidence_payload = b"EVIDENCE_PAYLOAD_FOR_RESTART_TEST_54321"
    store1.add_evidence(case.case_id, "disk.img", evidence_payload)

    run = RecoveryRun(
        run_id="run_restart_1",
        artifact_id=None,
        filename="notes.txt",
        format="txt",
        status="FULLY_RECOVERED",
        started_at=now,
        total_input_bytes=100,
        total_verified_bytes=100,
        total_reconstructed_bytes=0,
        total_missing_bytes=0,
        validation={"syntax": True},
        confidence={"total": 99.0},
    )
    store1.add_recovery_run(run)

    artifact_payload = b"RECOVERED_NOTES_CONTENT_ABCDEF"
    art = ArtifactResponse(
        artifact_id="art_restart_1",
        case_id=case.case_id,
        format="txt",
        size_bytes=len(artifact_payload),
        confidence_score=99,
        score_breakdown=ConfidenceBreakdownSchema(header_validity=100, footer_validity=100, structural_validation=100, size_plausibility=100, reconstruction_integrity=95, total=99),
        status="FULLY_RECOVERED",
        provenance=ArtifactProvenanceSchema(verified_bytes=len(artifact_payload), reconstructed_bytes=0, missing_bytes=0, reconstruction_method="NONE", validation_status="PASSED"),
        metadata={"run_id": "run_restart_1"},
    )
    store1.add_artifact(art)
    store1.store_artifact_bytes(art.artifact_id, artifact_payload)
    store1.link_artifact_to_run(art.artifact_id, run.run_id)

    # Standalone Pipeline B artifact
    standalone_payload = b"STANDALONE_FILE_PAYLOAD"
    store1.store_recovered_file("rec_file_restart", {
        "file_id": "rec_file_restart",
        "run_id": "run_restart_1",
        "format": "png",
        "status": "FULLY_RECOVERED",
        "confidence_score": 90.0,
    }, standalone_payload)

    # Close Session 1
    engine1.close()

    # ── Session 2: Reopen from file and assert exact state ─────────────────
    engine2 = SqliteEngine(db_file)
    store2 = SqliteStore(engine2)

    # 1. Verify Case
    retrieved_case = store2.get_case(case.case_id)
    assert retrieved_case is not None
    assert retrieved_case.name == "Restart Case"
    assert retrieved_case.artifact_count == 1
    assert retrieved_case.evidence is not None
    assert retrieved_case.evidence.file_size == len(evidence_payload)

    # 2. Verify Evidence Raw Bytes & Chunks
    ev_bytes = store2.get_evidence_bytes(case.case_id)
    assert ev_bytes == evidence_payload
    chunks = store2.get_evidence_chunks(case.case_id)
    assert chunks is not None
    assert len(chunks) >= 1
    assert chunks[0].data == evidence_payload

    # 3. Verify RecoveryRun
    retrieved_run = store2.get_recovery_run("run_restart_1")
    assert retrieved_run is not None
    assert retrieved_run.format == "txt"
    assert retrieved_run.confidence == {"total": 99.0}

    # 4. Verify Case Artifact & Bytes
    retrieved_art = store2.get_artifact("art_restart_1")
    assert retrieved_art is not None
    assert retrieved_art.confidence_score == 99
    art_bytes = store2.get_artifact_bytes("art_restart_1")
    assert art_bytes == artifact_payload

    # 5. Verify Authoritative Linkage
    linked_run = store2.get_recovery_run_by_artifact("art_restart_1")
    assert linked_run is not None
    assert linked_run.run_id == "run_restart_1"

    # 6. Verify Standalone Artifact & Bytes
    standalone_meta = store2.get_recovered_file_metadata("rec_file_restart")
    assert standalone_meta is not None
    assert standalone_meta["format"] == "png"
    assert store2.get_recovered_file_bytes("rec_file_restart") == standalone_payload

    engine2.close()


# ── Group E: Transaction Rollback Tests ───────────────────────────────────────

def test_e_add_evidence_atomic_rollback(mem_store):
    """Failure during chunk ingestion rolls back evidence record and raw blob."""
    case = mem_store.create_case("Rollback Evidence Case")
    payload = b"VALID_PAYLOAD_BYTES"

    # Monkeypatch chunk_evidence to simulate mid-operation crash
    from unittest.mock import patch

    with patch("backend.app.storage.sqlite_store.chunk_evidence", side_effect=RuntimeError("Simulated Chunker Crash")):
        with pytest.raises(RuntimeError, match="Simulated Chunker Crash"):
            mem_store.add_evidence(case.case_id, "crash.img", payload)

    # Assert no evidence metadata, chunks, or blobs were committed
    updated_case = mem_store.get_case(case.case_id)
    assert updated_case.evidence is None
    assert mem_store.get_evidence_bytes(case.case_id) is None
    assert mem_store.get_evidence_chunks(case.case_id) is None


def test_e_store_recovered_file_atomic_rollback(mem_store):
    """Failure during recovered file store rolls back record and raw blob."""
    from unittest.mock import patch

    with patch.object(mem_store, "link_artifact_to_run", side_effect=RuntimeError("Simulated Linkage Failure")):
        with pytest.raises(RuntimeError, match="Simulated Linkage Failure"):
            mem_store.store_recovered_file("crash_file", {
                "file_id": "crash_file",
                "run_id": "run_crash",
                "format": "txt",
            }, b"CRASH_BYTES")

    # Assert nothing survived
    assert mem_store.get_artifact("crash_file") is None
    assert mem_store.get_artifact_bytes("crash_file") is None


# ── Group F: Foreign Keys & Clear Safety ──────────────────────────────────────

def test_f_clear_all_tables_reverse_fk_order(mem_store):
    """clear() clears all stored state in reverse FK dependency order with 0 violations."""
    case = mem_store.create_case("Clear Test Case")
    mem_store.add_evidence(case.case_id, "ev.bin", b"evidence payload")

    run = RecoveryRun(
        run_id="run_clear", filename="t.txt", format="txt", status="FULLY_RECOVERED",
        started_at=datetime.now(timezone.utc), total_input_bytes=10, total_verified_bytes=10,
        total_reconstructed_bytes=0, total_missing_bytes=0,
    )
    mem_store.add_recovery_run(run)

    art = ArtifactResponse(
        artifact_id="art_clear", case_id=case.case_id, format="txt", size_bytes=10, confidence_score=100,
        score_breakdown=ConfidenceBreakdownSchema(header_validity=100, footer_validity=100, structural_validation=100, size_plausibility=100, reconstruction_integrity=100, total=100),
        status="FULLY_RECOVERED",
        provenance=ArtifactProvenanceSchema(verified_bytes=10, reconstructed_bytes=0, missing_bytes=0, reconstruction_method="NONE", validation_status="PASSED"),
        metadata={"run_id": "run_clear"},
    )
    mem_store.add_artifact(art)
    mem_store.store_artifact_bytes(art.artifact_id, b"art payload")

    # Clear storage
    mem_store.clear()

    # Verify all tables are empty
    with mem_store._engine.transaction() as cursor:
        for tbl in ["cases", "evidence_files", "evidence_chunks", "recovery_runs", "artifacts", "artifact_runs", "blobs"]:
            cursor.execute(f"SELECT COUNT(*) FROM {tbl};")
            assert cursor.fetchone()[0] == 0, f"Table {tbl} must be empty"

        # Verify zero foreign key violations
        cursor.execute("PRAGMA foreign_key_check;")
        violations = cursor.fetchall()
        assert len(violations) == 0, f"Foreign key check failed: {violations}"
