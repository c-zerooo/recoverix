"""
store.py — Storage facade and live application repository instance for Recoverix.

Re-exports repository contracts and provides the singleton `store` instance.
"""

from __future__ import annotations

from backend.app.storage.contracts import (
    BlobStore,
    CaseRepository,
    ArtifactRepository,
    RecoveryRunRepository,
)
from backend.app.storage.blob_store import InMemoryBlobStore
from backend.app.storage.memory_store import InMemoryStore, MAX_EVIDENCE_SIZE
from backend.app.storage.sqlite_store import SqliteStore

# Global live store instance (SQLite repository implementation)
store = SqliteStore()

__all__ = [
    "MAX_EVIDENCE_SIZE",
    "BlobStore",
    "CaseRepository",
    "ArtifactRepository",
    "RecoveryRunRepository",
    "InMemoryBlobStore",
    "InMemoryStore",
    "SqliteStore",
    "store",
]
