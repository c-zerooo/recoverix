"""
sqlite_blob_store.py — SQLite-backed implementation of the BlobStore contract.

Stores raw binary payloads (evidence content, recovered artifact bytes) directly
in SQLite BLOB storage with exact binary fidelity, atomic upserts, and transactional isolation.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from backend.app.storage.sqlite_engine import SqliteEngine


class SqliteBlobStore:
    """Thread-safe SQLite implementation of the BlobStore contract."""

    def __init__(self, engine: SqliteEngine) -> None:
        """Initialize with a SqliteEngine instance."""
        if not isinstance(engine, SqliteEngine):
            raise TypeError("engine must be an instance of SqliteEngine")
        self._engine = engine

    def put(self, key: str, data: bytes) -> None:
        """Store a binary blob under key with atomic overwrite semantics."""
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Blob key must be a non-empty string")
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("Blob data must be bytes-like")

        raw_bytes = bytes(data)
        size_bytes = len(raw_bytes)
        created_at = datetime.now(timezone.utc).isoformat()

        with self._engine.transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO blobs (blob_key, data, size_bytes, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(blob_key) DO UPDATE SET
                    data = excluded.data,
                    size_bytes = excluded.size_bytes,
                    created_at = excluded.created_at;
                """,
                (key, sqlite3.Binary(raw_bytes), size_bytes, created_at),
            )

    def get(self, key: str) -> Optional[bytes]:
        """Retrieve binary blob for key, or None if not found."""
        if not isinstance(key, str) or not key.strip():
            return None

        with self._engine.transaction() as cursor:
            cursor.execute("SELECT data FROM blobs WHERE blob_key = ?;", (key,))
            row = cursor.fetchone()
            if row is None:
                return None
            val = row["data"] if isinstance(row, sqlite3.Row) else row[0]
            return bytes(val)

    def delete(self, key: str) -> bool:
        """Delete binary blob for key. Returns True if deleted, False if not found."""
        if not isinstance(key, str) or not key.strip():
            return False

        with self._engine.transaction() as cursor:
            cursor.execute("DELETE FROM blobs WHERE blob_key = ?;", (key,))
            return cursor.rowcount > 0

    def exists(self, key: str) -> bool:
        """Check if binary blob exists for key."""
        if not isinstance(key, str) or not key.strip():
            return False

        with self._engine.transaction() as cursor:
            cursor.execute("SELECT 1 FROM blobs WHERE blob_key = ? LIMIT 1;", (key,))
            return cursor.fetchone() is not None

    def clear(self) -> None:
        """Clear all stored blobs atomically."""
        with self._engine.transaction() as cursor:
            cursor.execute("DELETE FROM blobs;")

    def __len__(self) -> int:
        """Return the count of stored blobs."""
        with self._engine.transaction() as cursor:
            cursor.execute("SELECT COUNT(*) FROM blobs;")
            row = cursor.fetchone()
            return int(row[0]) if row else 0
