"""
reader.py — Safe evidence file reader.

Accepts a filesystem path, validates it, and reads the raw bytes into
memory with strict size and type checks.  Returns an immutable bytes
object suitable for deterministic downstream processing.

This module does NOT perform recovery, carving, reconstruction,
classification, or AI work.
"""

from __future__ import annotations

from pathlib import Path

from backend.app.generator.disk import MAX_EVIDENCE_SIZE


class EvidenceReader:
    """Read and validate a raw evidence image from disk.

    Usage::

        reader = EvidenceReader(Path("backend/generated/damaged.img"))
        raw: bytes = reader.data
        filename: str = reader.filename
    """

    def __init__(self, path: Path | str) -> None:
        """Load and validate the evidence file at *path*.

        Args:
            path: Filesystem path to the evidence image.

        Raises:
            FileNotFoundError: If *path* does not exist.
            IsADirectoryError: If *path* is a directory.
            ValueError: If the file is empty or exceeds MAX_EVIDENCE_SIZE.
        """
        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"Evidence file not found: {path}")

        if path.is_dir():
            raise IsADirectoryError(
                f"Expected a regular file, got a directory: {path}"
            )

        # Check size before reading to avoid loading unbounded input.
        file_size = path.stat().st_size

        if file_size == 0:
            raise ValueError(f"Evidence file is empty: {path}")

        if file_size > MAX_EVIDENCE_SIZE:
            raise ValueError(
                f"Evidence file size {file_size:,} bytes exceeds "
                f"hard limit ({MAX_EVIDENCE_SIZE:,} bytes / "
                f"{MAX_EVIDENCE_SIZE / 1024 / 1024:.0f} MiB): {path}"
            )

        self._data: bytes = path.read_bytes()
        self._filename: str = path.name
        self._path: Path = path.resolve()

    # ── properties ──────────────────────────────────────────────────

    @property
    def data(self) -> bytes:
        """Raw evidence bytes (immutable)."""
        return self._data

    @property
    def filename(self) -> str:
        """Original filename of the evidence image."""
        return self._filename

    @property
    def size(self) -> int:
        """Evidence size in bytes."""
        return len(self._data)

    @property
    def path(self) -> Path:
        """Resolved absolute path to the evidence file."""
        return self._path
