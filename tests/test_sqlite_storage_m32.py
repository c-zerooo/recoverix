"""
test_sqlite_storage_m32.py — Test Suite for Milestone 3.2.1 SQLite Engine & BlobStore.

Verifies:
A. File-backed database creation (directory creation, file creation)
B. In-memory database (':memory:' operation without filesystem side-effects)
C. PRAGMA configuration (foreign_keys, busy_timeout, WAL, synchronous NORMAL)
D. Transaction commit (data persistence across clean context exits)
E. Transaction rollback (atomic rollback on exceptions)
F. Blob put/get (exact binary round-trip)
G. Binary edge cases (empty bytes b'', full byte spectrum 0-255, null bytes, 1 MiB buffer)
H. Blob overwrite (atomic replace, size update, count unchanged)
I. Blob delete (returns True for existing, False for missing)
J. Blob exists (correct presence detection)
K. Blob clear (atomic wipe of all blobs)
L. Persistence across separate connections (close engine, reopen file, retrieve payload)
M. Foreign-key enforcement (PRAGMA foreign_keys = ON rejects orphans with IntegrityError)
N. Idempotent initialization (multiple initialize() calls preserve existing schema and data)
O. Transaction failure isolation (multiple operations fail midway, complete rollback)
P. BlobStore protocol conformance (runtime checkable Protocol validation)
Q. Key & type validation (invalid keys raise ValueError, non-bytes raise TypeError)
R. Environment variable configuration (RECOVERIX_DB_PATH override)
S. Engine lifecycle (closed engine raises RuntimeError)
T. Safe table clearing (clear_all_tables() executes in reverse foreign-key order)
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import pytest

from backend.app.storage.contracts import BlobStore
from backend.app.storage.sqlite_engine import SqliteEngine
from backend.app.storage.sqlite_blob_store import SqliteBlobStore


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def mem_engine() -> SqliteEngine:
    """Fixture providing an initialized in-memory SqliteEngine."""
    engine = SqliteEngine(":memory:")
    engine.initialize()
    yield engine
    engine.close()


@pytest.fixture
def file_engine(tmp_path) -> SqliteEngine:
    """Fixture providing an initialized file-backed SqliteEngine."""
    db_path = str(tmp_path / "test_recoverix.db")
    engine = SqliteEngine(db_path)
    engine.initialize()
    yield engine
    engine.close()


@pytest.fixture
def mem_blob_store(mem_engine) -> SqliteBlobStore:
    """Fixture providing a SqliteBlobStore backed by in-memory engine."""
    return SqliteBlobStore(mem_engine)


@pytest.fixture
def file_blob_store(file_engine) -> SqliteBlobStore:
    """Fixture providing a SqliteBlobStore backed by file engine."""
    return SqliteBlobStore(file_engine)


# ── Test A: File-backed Database Creation ─────────────────────────────────────

def test_a_file_backed_database_creation(tmp_path):
    """A. File-backed database and nested parent directories are created automatically."""
    nested_dir = tmp_path / "deeply" / "nested" / "path"
    db_file = nested_dir / "recoverix_test.db"
    assert not nested_dir.exists()

    engine = SqliteEngine(str(db_file))
    assert nested_dir.exists()
    assert nested_dir.is_dir()

    engine.initialize()
    assert db_file.exists()
    assert db_file.is_file()
    assert os.path.getsize(str(db_file)) > 0

    engine.close()


# ── Test B: In-memory Database ────────────────────────────────────────────────

def test_b_in_memory_database():
    """B. In-memory ':memory:' engine operates without creating any filesystem paths."""
    engine = SqliteEngine(":memory:")
    assert engine._is_memory is True
    engine.initialize()

    with engine.transaction() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
        tables = [row["name"] for row in cursor.fetchall()]

    assert "cases" in tables
    assert "blobs" in tables
    assert "recovery_runs" in tables
    assert "artifacts" in tables
    assert "artifact_runs" in tables

    engine.close()


# ── Test C: PRAGMA Configuration ─────────────────────────────────────────────

def test_c_pragma_configuration_file_backed(file_engine):
    """C. Verify foreign_keys=ON, busy_timeout=5000, WAL mode, and synchronous=NORMAL on file DB."""
    conn = file_engine.connect()
    try:
        fk = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
        bt = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
        jm = conn.execute("PRAGMA journal_mode;").fetchone()[0].lower()
        sync = conn.execute("PRAGMA synchronous;").fetchone()[0]

        assert fk == 1, "foreign_keys must be ON"
        assert bt == 5000, "busy_timeout must be 5000ms"
        assert jm == "wal", "journal_mode must be WAL"
        assert sync == 1, "synchronous must be 1 (NORMAL)"
    finally:
        conn.close()


def test_c_pragma_configuration_in_memory(mem_engine):
    """C. Verify foreign_keys=ON and busy_timeout=5000 on in-memory DB."""
    conn = mem_engine.connect()
    try:
        fk = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
        bt = conn.execute("PRAGMA busy_timeout;").fetchone()[0]

        assert fk == 1, "foreign_keys must be ON for in-memory"
        assert bt == 5000, "busy_timeout must be 5000ms for in-memory"
    finally:
        conn.close()


# ── Test D: Transaction Commit ───────────────────────────────────────────────

def test_d_transaction_commit(mem_engine):
    """D. Data inserted within transaction survives clean context exit."""
    with mem_engine.transaction() as cursor:
        cursor.execute(
            "INSERT INTO cases (case_id, name, description, created_at) "
            "VALUES (?, ?, ?, ?);",
            ("case_001", "Forensic Investigation 1", "Desc", "2026-09-29T00:00:00Z"),
        )

    # Query in a subsequent transaction
    with mem_engine.transaction() as cursor:
        cursor.execute("SELECT name, description FROM cases WHERE case_id = ?;", ("case_001",))
        row = cursor.fetchone()
        assert row is not None
        assert row["name"] == "Forensic Investigation 1"
        assert row["description"] == "Desc"


# ── Test E: Transaction Rollback ─────────────────────────────────────────────

def test_e_transaction_rollback(mem_engine):
    """E. Exception inside transaction rolls back all inserted changes."""
    with pytest.raises(RuntimeError, match="Simulated crash"):
        with mem_engine.transaction() as cursor:
            cursor.execute(
                "INSERT INTO cases (case_id, name, description, created_at) "
                "VALUES (?, ?, ?, ?);",
                ("case_fail", "Rollback Case", "Should not exist", "2026-09-29T00:00:00Z"),
            )
            raise RuntimeError("Simulated crash")

    # Verify row does not exist
    with mem_engine.transaction() as cursor:
        cursor.execute("SELECT * FROM cases WHERE case_id = ?;", ("case_fail",))
        row = cursor.fetchone()
        assert row is None


# ── Test F: Blob Put/Get ─────────────────────────────────────────────────────

def test_f_blob_put_get(mem_blob_store):
    """F. Put and get round-trip preserves exact binary payload."""
    payload = b"Exact forensic artifact bytes\r\n\x00Header\xff"
    mem_blob_store.put("artifact:art_001", payload)

    retrieved = mem_blob_store.get("artifact:art_001")
    assert retrieved == payload
    assert isinstance(retrieved, bytes)


# ── Test G: Binary Edge Cases ────────────────────────────────────────────────

def test_g_binary_edge_cases(mem_blob_store):
    """G. Handle empty bytes, null bytes, full byte spectrum, and larger buffers."""
    # 1. Empty bytes
    mem_blob_store.put("blob:empty", b"")
    assert mem_blob_store.get("blob:empty") == b""
    assert mem_blob_store.exists("blob:empty") is True

    # 2. Null bytes and full spectrum
    full_spectrum = bytes(range(256))
    mem_blob_store.put("blob:spectrum", full_spectrum)
    assert mem_blob_store.get("blob:spectrum") == full_spectrum

    # 3. Embedded nulls
    null_bytes = b"\x00\x00\x00\x01\x00\x02\x00\x00"
    mem_blob_store.put("blob:nulls", null_bytes)
    assert mem_blob_store.get("blob:nulls") == null_bytes

    # 4. Larger buffer (1 MiB pseudo-random binary payload)
    large_payload = os.urandom(1024 * 1024)
    mem_blob_store.put("blob:large", large_payload)
    retrieved_large = mem_blob_store.get("blob:large")
    assert retrieved_large is not None
    assert len(retrieved_large) == 1024 * 1024
    assert hashlib.sha256(retrieved_large).hexdigest() == hashlib.sha256(large_payload).hexdigest()


# ── Test H: Blob Overwrite ───────────────────────────────────────────────────

def test_h_blob_overwrite(mem_blob_store):
    """H. Overwriting an existing key replaces bytes and updates length without creating duplicates."""
    mem_blob_store.put("evidence:ev_1", b"Initial version of evidence")
    assert len(mem_blob_store) == 1
    assert mem_blob_store.get("evidence:ev_1") == b"Initial version of evidence"

    mem_blob_store.put("evidence:ev_1", b"Updated replacement evidence bytes")
    assert len(mem_blob_store) == 1
    assert mem_blob_store.get("evidence:ev_1") == b"Updated replacement evidence bytes"


# ── Test I: Blob Delete ──────────────────────────────────────────────────────

def test_i_blob_delete(mem_blob_store):
    """I. Delete returns True for existing key, False for missing key."""
    mem_blob_store.put("blob:to_del", b"Temporary data")
    assert mem_blob_store.exists("blob:to_del") is True

    # First delete returns True
    assert mem_blob_store.delete("blob:to_del") is True
    assert mem_blob_store.get("blob:to_del") is None
    assert mem_blob_store.exists("blob:to_del") is False

    # Second delete returns False
    assert mem_blob_store.delete("blob:to_del") is False
    assert mem_blob_store.delete("non_existent_key") is False


# ── Test J: Blob Exists ──────────────────────────────────────────────────────

def test_j_blob_exists(mem_blob_store):
    """J. Correctly reports presence and absence of blobs."""
    assert mem_blob_store.exists("missing_key") is False

    mem_blob_store.put("present_key", b"Data")
    assert mem_blob_store.exists("present_key") is True

    mem_blob_store.delete("present_key")
    assert mem_blob_store.exists("present_key") is False


# ── Test K: Blob Clear ───────────────────────────────────────────────────────

def test_k_blob_clear(mem_blob_store):
    """K. Clear deletes all stored blobs atomically."""
    mem_blob_store.put("k1", b"v1")
    mem_blob_store.put("k2", b"v2")
    mem_blob_store.put("k3", b"v3")
    assert len(mem_blob_store) == 3

    mem_blob_store.clear()
    assert len(mem_blob_store) == 0
    assert mem_blob_store.get("k1") is None
    assert mem_blob_store.get("k2") is None
    assert mem_blob_store.get("k3") is None


# ── Test L: Persistence Across Separate Connections ──────────────────────────

def test_l_persistence_across_separate_connections(tmp_path):
    """L. Data written via SqliteBlobStore survives closing engine and reopening with a new engine."""
    db_path = str(tmp_path / "persistent_test.db")
    payload = b"Forensic payload intended to survive process restart"

    # Step 1: Open first engine, initialize, store blob, and close
    engine1 = SqliteEngine(db_path)
    engine1.initialize()
    store1 = SqliteBlobStore(engine1)
    store1.put("persistent_key", payload)
    assert store1.get("persistent_key") == payload
    engine1.close()

    # Step 2: Open second engine pointing to same file, read blob
    engine2 = SqliteEngine(db_path)
    store2 = SqliteBlobStore(engine2)
    retrieved = store2.get("persistent_key")
    assert retrieved == payload
    assert store2.exists("persistent_key") is True
    assert len(store2) == 1
    engine2.close()


# ── Test M: Foreign-key Enforcement ──────────────────────────────────────────

def test_m_foreign_key_enforcement(mem_engine):
    """M. PRAGMA foreign_keys = ON rejects orphan child rows across relational tables."""
    # 1. Reject evidence_files referencing non-existent case
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        with mem_engine.transaction() as cursor:
            cursor.execute(
                "INSERT INTO evidence_files (case_id, filename, file_size, uploaded_at, sha256) "
                "VALUES (?, ?, ?, ?, ?);",
                ("orphan_case", "file.bin", 100, "2026-09-29T00:00:00Z", "abc123sha"),
            )

    # 2. Reject evidence_chunks referencing non-existent case
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        with mem_engine.transaction() as cursor:
            cursor.execute(
                "INSERT INTO evidence_chunks (chunk_id, case_id, chunk_index, offset, size, sha256) "
                "VALUES (?, ?, ?, ?, ?, ?);",
                ("chk_orphan", "orphan_case", 0, 0, 4096, "abc123sha"),
            )

    # 3. Reject artifact_runs referencing non-existent recovery_runs
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        with mem_engine.transaction() as cursor:
            cursor.execute(
                "INSERT INTO artifact_runs (artifact_id, run_id) "
                "VALUES (?, ?);",
                ("art_orphan", "non_existent_run"),
            )


# ── Test N: Idempotent Initialization ────────────────────────────────────────

def test_n_idempotent_initialization(file_engine):
    """N. Running initialize() multiple times is safe and preserves existing data."""
    store = SqliteBlobStore(file_engine)
    store.put("key_survivor", b"Should survive re-initialization")

    # Insert case data
    with file_engine.transaction() as cursor:
        cursor.execute(
            "INSERT INTO cases (case_id, name, created_at) VALUES (?, ?, ?);",
            ("case_keep", "Case to Keep", "2026-09-29T00:00:00Z"),
        )

    # Re-initialize multiple times
    file_engine.initialize()
    file_engine.initialize()

    # Verify all data remains intact
    assert store.get("key_survivor") == b"Should survive re-initialization"
    with file_engine.transaction() as cursor:
        cursor.execute("SELECT name FROM cases WHERE case_id = ?;", ("case_keep",))
        row = cursor.fetchone()
        assert row is not None
        assert row["name"] == "Case to Keep"


# ── Test O: Transaction Failure Isolation ────────────────────────────────────

def test_o_transaction_failure_isolation(mem_engine):
    """O. Multi-operation transaction failure rolls back all operations in that block."""
    with mem_engine.transaction() as cursor:
        cursor.execute(
            "INSERT INTO cases (case_id, name, created_at) VALUES (?, ?, ?);",
            ("case_prior", "Prior Case", "2026-09-29T00:00:00Z"),
        )

    # Run a compound transaction that inserts a case and a blob, then fails midway
    with pytest.raises(ValueError, match="Intentional failure midway"):
        with mem_engine.transaction() as cursor:
            cursor.execute(
                "INSERT INTO cases (case_id, name, created_at) VALUES (?, ?, ?);",
                ("case_compound", "Compound Case", "2026-09-29T00:00:00Z"),
            )
            cursor.execute(
                "INSERT INTO blobs (blob_key, data, size_bytes, created_at) VALUES (?, ?, ?, ?);",
                ("blob_compound", sqlite3.Binary(b"Compound data"), 13, "2026-09-29T00:00:00Z"),
            )
            raise ValueError("Intentional failure midway")

    # Verify: prior case remains, compound case and compound blob were both rolled back
    with mem_engine.transaction() as cursor:
        cursor.execute("SELECT case_id FROM cases WHERE case_id = ?;", ("case_prior",))
        assert cursor.fetchone() is not None

        cursor.execute("SELECT case_id FROM cases WHERE case_id = ?;", ("case_compound",))
        assert cursor.fetchone() is None

        cursor.execute("SELECT blob_key FROM blobs WHERE blob_key = ?;", ("blob_compound",))
        assert cursor.fetchone() is None


# ── Test P: BlobStore Protocol Conformance ───────────────────────────────────

def test_p_blob_store_protocol_conformance(mem_blob_store):
    """P. SqliteBlobStore conforms to runtime_checkable BlobStore protocol."""
    assert isinstance(mem_blob_store, BlobStore)


# ── Test Q: Key & Type Validation ────────────────────────────────────────────

def test_q_blob_store_validation(mem_blob_store):
    """Q. Key and type validations reject malformed inputs."""
    # Empty or whitespace key
    with pytest.raises(ValueError, match="non-empty string"):
        mem_blob_store.put("", b"data")
    with pytest.raises(ValueError, match="non-empty string"):
        mem_blob_store.put("   ", b"data")
    with pytest.raises(ValueError, match="non-empty string"):
        mem_blob_store.put(123, b"data")  # type: ignore

    # Non-bytes data
    with pytest.raises(TypeError, match="bytes-like"):
        mem_blob_store.put("valid_key", "string_payload")  # type: ignore

    # Safe get/delete/exists behavior on invalid keys
    assert mem_blob_store.get("") is None
    assert mem_blob_store.get("  ") is None
    assert mem_blob_store.delete("") is False
    assert mem_blob_store.exists("") is False


# ── Test R: Environment Variable Configuration ───────────────────────────────

def test_r_environment_variable_db_path(tmp_path, monkeypatch):
    """R. RECOVERIX_DB_PATH environment variable is respected when db_path is omitted."""
    custom_path = str(tmp_path / "env_custom.db")
    monkeypatch.setenv("RECOVERIX_DB_PATH", custom_path)

    engine = SqliteEngine()
    assert engine.db_path == custom_path
    engine.initialize()
    assert os.path.exists(custom_path)
    engine.close()


# ── Test S: Closed Engine Lifecycle ──────────────────────────────────────────

def test_s_closed_engine_raises(mem_engine):
    """S. Methods on a closed engine raise RuntimeError."""
    mem_engine.close()
    with pytest.raises(RuntimeError, match="SqliteEngine is closed"):
        mem_engine.connect()

    with pytest.raises(RuntimeError, match="SqliteEngine is closed"):
        with mem_engine.transaction():
            pass

    with pytest.raises(RuntimeError, match="SqliteEngine is closed"):
        mem_engine.initialize()


# ── Test T: Safe Table Clearing ──────────────────────────────────────────────

def test_t_clear_all_tables_reverse_fk_order(mem_engine):
    """T. clear_all_tables() clears all relational tables in reverse dependency order."""
    # Insert a full relational hierarchy
    with mem_engine.transaction() as cursor:
        cursor.execute(
            "INSERT INTO cases (case_id, name, created_at) VALUES (?, ?, ?);",
            ("case_hier", "Hierarchy Case", "2026-09-29T00:00:00Z"),
        )
        cursor.execute(
            "INSERT INTO evidence_files (case_id, filename, file_size, uploaded_at, sha256) "
            "VALUES (?, ?, ?, ?, ?);",
            ("case_hier", "ev.bin", 100, "2026-09-29T00:00:00Z", "sha123"),
        )
        cursor.execute(
            "INSERT INTO evidence_chunks (chunk_id, case_id, chunk_index, offset, size, sha256) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            ("chk_1", "case_hier", 0, 0, 100, "sha123"),
        )
        cursor.execute(
            "INSERT INTO recovery_runs (run_id, case_id, filename, format, status, started_at, "
            "total_input_bytes, total_verified_bytes, total_reconstructed_bytes, total_missing_bytes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
            ("run_hier", "case_hier", "rec.txt", "txt", "SUCCESS", "2026-09-29T00:00:00Z", 100, 100, 0, 0),
        )
        cursor.execute(
            "INSERT INTO artifacts (artifact_id, case_id, run_id, format, status, confidence_score) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            ("art_hier", "case_hier", "run_hier", "txt", "SUCCESS", 100.0),
        )
        cursor.execute(
            "INSERT INTO artifact_runs (artifact_id, run_id) VALUES (?, ?);",
            ("art_hier", "run_hier"),
        )
        cursor.execute(
            "INSERT INTO blobs (blob_key, data, size_bytes, created_at) VALUES (?, ?, ?, ?);",
            ("blob_hier", sqlite3.Binary(b"payload"), 7, "2026-09-29T00:00:00Z"),
        )

    # Clear all tables without FK violations
    mem_engine.clear_all_tables()

    # Verify all tables are empty
    with mem_engine.transaction() as cursor:
        for tbl in ["cases", "evidence_files", "evidence_chunks", "recovery_runs", "artifacts", "artifact_runs", "blobs"]:
            cursor.execute(f"SELECT COUNT(*) FROM {tbl};")
            count = cursor.fetchone()[0]
            assert count == 0, f"Table {tbl} must be empty after clear_all_tables"
