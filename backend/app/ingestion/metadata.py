"""
metadata.py — Deterministic evidence metadata.

Computes and stores identity metadata for an ingested evidence image:
filename, byte size, SHA-256 digest, chunk size, and chunk count.

All values are deterministic — the same bytes always produce the same
metadata.

This module does NOT perform recovery, carving, reconstruction,
classification, or AI work.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from backend.app.ingestion.chunker import DEFAULT_CHUNK_SIZE


@dataclass(frozen=True)
class EvidenceMetadata:
    """Immutable identity metadata for an ingested evidence image."""

    filename: str
    size_bytes: int
    sha256: str
    chunk_size: int
    num_chunks: int


def compute_metadata(
    data: bytes,
    filename: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> EvidenceMetadata:
    """Compute deterministic metadata for raw evidence *data*.

    Args:
        data: Raw evidence bytes.
        filename: Original filename of the evidence image.
        chunk_size: Size of each fixed-size chunk in bytes.

    Returns:
        An immutable EvidenceMetadata record.

    Raises:
        ValueError: If *data* is empty or *chunk_size* is invalid.
    """
    if len(data) == 0:
        raise ValueError("Cannot compute metadata for empty evidence")
    if chunk_size <= 0:
        raise ValueError(f"Chunk size must be positive, got {chunk_size}")

    size_bytes = len(data)
    sha256_hex = hashlib.sha256(data).hexdigest()
    num_chunks = math.ceil(size_bytes / chunk_size)

    return EvidenceMetadata(
        filename=filename,
        size_bytes=size_bytes,
        sha256=sha256_hex,
        chunk_size=chunk_size,
        num_chunks=num_chunks,
    )
