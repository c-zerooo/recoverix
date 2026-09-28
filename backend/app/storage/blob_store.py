"""
blob_store.py — In-memory implementation of the BlobStore contract.
"""

from __future__ import annotations

import threading
from typing import Dict, Optional


class InMemoryBlobStore:
    """Thread-safe in-memory store for raw binary blobs (evidence or artifact bytes)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._blobs: Dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> None:
        """Store a binary blob under key."""
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Blob key must be a non-empty string")
        with self._lock:
            self._blobs[key] = bytes(data)

    def get(self, key: str) -> Optional[bytes]:
        """Retrieve binary blob for key, or None if not found."""
        with self._lock:
            blob = self._blobs.get(key)
            return bytes(blob) if blob is not None else None

    def delete(self, key: str) -> bool:
        """Delete binary blob for key. Returns True if deleted, False if not found."""
        with self._lock:
            return self._blobs.pop(key, None) is not None

    def exists(self, key: str) -> bool:
        """Check if binary blob exists for key."""
        with self._lock:
            return key in self._blobs

    def clear(self) -> None:
        """Clear all stored blobs."""
        with self._lock:
            self._blobs.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._blobs)
