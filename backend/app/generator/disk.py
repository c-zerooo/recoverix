"""
disk.py — Low-level evidence image buffer.

Provides a fixed-size byte buffer that represents a synthetic forensic
evidence image.  All writes are bounds-checked.  Nothing is written to
disk until `save()` is called.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

# Hard safety limit — the generator refuses to create images above this.
MAX_EVIDENCE_SIZE: int = 5 * 1024 * 1024  # 5 MiB


class EvidenceDisk:
    """Fixed-size, bounds-checked byte buffer for synthetic evidence."""

    def __init__(self, size: int, *, fill: int = 0x00) -> None:
        """Create an evidence image of *size* bytes, filled with *fill*.

        Args:
            size: Total image size in bytes.  Must be 1 … MAX_EVIDENCE_SIZE.
            fill: Byte value used to initialise every position (0x00–0xFF).

        Raises:
            ValueError: If *size* or *fill* is out of range.
        """
        if size <= 0:
            raise ValueError(f"Evidence size must be positive, got {size}")
        if size > MAX_EVIDENCE_SIZE:
            raise ValueError(
                f"Evidence size {size} exceeds hard limit "
                f"({MAX_EVIDENCE_SIZE} bytes / {MAX_EVIDENCE_SIZE / 1024 / 1024:.0f} MiB)"
            )
        if not (0 <= fill <= 0xFF):
            raise ValueError(f"Fill byte must be 0x00–0xFF, got {fill:#x}")

        self._data = bytearray([fill]) * size
        self._size = size

    # ── properties ──────────────────────────────────────────────────────

    @property
    def size(self) -> int:
        """Total image size in bytes."""
        return self._size

    @property
    def data(self) -> bytes:
        """Immutable snapshot of the current image contents."""
        return bytes(self._data)

    # ── write / read ────────────────────────────────────────────────────

    def write(self, offset: int, payload: bytes) -> None:
        """Write *payload* at *offset*, with strict bounds checking.

        Raises:
            ValueError: If the write would start before 0 or extend past
                        the end of the image.
        """
        if offset < 0:
            raise ValueError(f"Negative offset: {offset}")
        end = offset + len(payload)
        if end > self._size:
            raise ValueError(
                f"Write at offset {offset} with length {len(payload)} "
                f"exceeds image size {self._size} (end={end})"
            )
        self._data[offset:end] = payload

    def read(self, offset: int, length: int) -> bytes:
        """Read *length* bytes starting at *offset*.

        Raises:
            ValueError: If the read region is out of bounds.
        """
        if offset < 0:
            raise ValueError(f"Negative offset: {offset}")
        if length < 0:
            raise ValueError(f"Negative length: {length}")
        end = offset + length
        if end > self._size:
            raise ValueError(
                f"Read at offset {offset} with length {length} "
                f"exceeds image size {self._size}"
            )
        return bytes(self._data[offset:end])

    # ── persistence ─────────────────────────────────────────────────────

    def sha256(self) -> str:
        """Return the hex-encoded SHA-256 digest of the image."""
        return hashlib.sha256(self._data).hexdigest()

    def save(self, path: Path | str) -> Path:
        """Write the image to *path*, creating parent directories.

        Returns:
            The resolved path that was written.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self._data)
        return path.resolve()
