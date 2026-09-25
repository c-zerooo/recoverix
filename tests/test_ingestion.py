"""
test_ingestion.py — Tests for the Recoverix evidence ingestion layer.

Covers: evidence reading, metadata computation, fixed-size chunking,
edge cases (empty, oversized, directory, missing), determinism,
chunk validation, and integration with the generator.
"""

from __future__ import annotations

import hashlib
import math
import sys
from pathlib import Path

import pytest

# Ensure imports work from the project root.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.app.generator.disk import MAX_EVIDENCE_SIZE
from backend.app.ingestion.reader import EvidenceReader
from backend.app.ingestion.metadata import EvidenceMetadata, compute_metadata
from backend.app.ingestion.chunker import Chunk, chunk_evidence, DEFAULT_CHUNK_SIZE


# ── Helpers ─────────────────────────────────────────────────────────

def _write_file(path: Path, data: bytes) -> Path:
    """Write *data* to *path*, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


# ── 1. EvidenceReader loads a valid file ─────────────────────────────

def test_reader_loads_valid_file(tmp_path):
    content = b"EVIDENCE" * 100
    img = _write_file(tmp_path / "test.img", content)

    reader = EvidenceReader(img)

    assert reader.data == content
    assert reader.filename == "test.img"
    assert reader.size == len(content)
    assert reader.path == img.resolve()


# ── 2. EvidenceReader rejects missing file ───────────────────────────

def test_reader_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="not found"):
        EvidenceReader(tmp_path / "nonexistent.img")


# ── 3. EvidenceReader rejects directory ──────────────────────────────

def test_reader_rejects_directory(tmp_path):
    d = tmp_path / "subdir"
    d.mkdir()
    with pytest.raises(IsADirectoryError, match="directory"):
        EvidenceReader(d)


# ── 4. EvidenceReader rejects empty file ─────────────────────────────

def test_reader_rejects_empty_file(tmp_path):
    empty = _write_file(tmp_path / "empty.img", b"")
    with pytest.raises(ValueError, match="empty"):
        EvidenceReader(empty)


# ── 5. EvidenceReader rejects oversized file ─────────────────────────

def test_reader_rejects_oversized_file(tmp_path):
    # Create a file one byte over the limit.
    oversized = _write_file(tmp_path / "big.img", b"\x00" * (MAX_EVIDENCE_SIZE + 1))
    with pytest.raises(ValueError, match="exceeds"):
        EvidenceReader(oversized)


# ── 6. EvidenceReader accepts string path ────────────────────────────

def test_reader_accepts_string_path(tmp_path):
    content = b"STRINGPATH"
    img = _write_file(tmp_path / "str.img", content)
    reader = EvidenceReader(str(img))
    assert reader.data == content


# ── 7. Metadata computation is deterministic ─────────────────────────

def test_metadata_determinism():
    data = b"A" * 8192
    m1 = compute_metadata(data, "a.img")
    m2 = compute_metadata(data, "a.img")
    assert m1 == m2


# ── 8. Metadata fields are correct ──────────────────────────────────

def test_metadata_fields():
    data = b"\xff" * 10000
    meta = compute_metadata(data, "evidence.img", chunk_size=4096)

    assert meta.filename == "evidence.img"
    assert meta.size_bytes == 10000
    assert meta.sha256 == hashlib.sha256(data).hexdigest()
    assert meta.chunk_size == 4096
    assert meta.num_chunks == math.ceil(10000 / 4096)  # 3


# ── 9. Metadata rejects empty data ──────────────────────────────────

def test_metadata_rejects_empty():
    with pytest.raises(ValueError, match="empty"):
        compute_metadata(b"", "empty.img")


# ── 10. Metadata rejects invalid chunk size ──────────────────────────

def test_metadata_rejects_invalid_chunk_size():
    with pytest.raises(ValueError, match="positive"):
        compute_metadata(b"data", "a.img", chunk_size=0)
    with pytest.raises(ValueError, match="positive"):
        compute_metadata(b"data", "a.img", chunk_size=-1)


# ── 11. chunk_evidence produces correct chunks ──────────────────────

def test_chunk_evidence_exact_multiple():
    """Data length is an exact multiple of chunk size → no partial chunk."""
    data = bytes(range(256)) * 4  # 1024 bytes
    chunks = chunk_evidence(data, chunk_size=256)

    assert len(chunks) == 4
    for i, c in enumerate(chunks):
        assert c.index == i
        assert c.offset == i * 256
        assert c.length == 256
        assert c.data == data[i * 256 : (i + 1) * 256]


def test_chunk_evidence_partial_tail():
    """Data length is not a multiple of chunk size → final chunk is shorter."""
    data = b"X" * 1000
    chunks = chunk_evidence(data, chunk_size=400)

    assert len(chunks) == 3  # 400 + 400 + 200
    assert chunks[0].length == 400
    assert chunks[1].length == 400
    assert chunks[2].length == 200
    assert chunks[2].data == b"X" * 200


# ── 12. chunk_evidence covers entire evidence ───────────────────────

def test_chunks_cover_full_evidence():
    data = b"\xAB" * 5000
    chunks = chunk_evidence(data, chunk_size=700)

    reassembled = b"".join(c.data for c in chunks)
    assert reassembled == data


# ── 13. chunk_evidence rejects empty data ────────────────────────────

def test_chunk_evidence_rejects_empty():
    with pytest.raises(ValueError, match="empty"):
        chunk_evidence(b"")


# ── 14. chunk_evidence rejects invalid chunk size ────────────────────

def test_chunk_evidence_rejects_invalid_chunk_size():
    with pytest.raises(ValueError, match="positive"):
        chunk_evidence(b"data", chunk_size=0)
    with pytest.raises(ValueError, match="positive"):
        chunk_evidence(b"data", chunk_size=-5)


# ── 15. Chunk.validate catches structural errors ─────────────────────

class TestChunkValidation:
    def test_negative_index(self):
        c = Chunk(index=-1, offset=0, length=4, data=b"abcd")
        with pytest.raises(ValueError, match="non-negative"):
            c.validate(100)

    def test_negative_offset(self):
        c = Chunk(index=0, offset=-1, length=4, data=b"abcd")
        with pytest.raises(ValueError, match="non-negative"):
            c.validate(100)

    def test_zero_length(self):
        c = Chunk(index=0, offset=0, length=0, data=b"")
        with pytest.raises(ValueError, match="positive"):
            c.validate(100)

    def test_exceeds_evidence(self):
        c = Chunk(index=0, offset=90, length=20, data=b"\x00" * 20)
        with pytest.raises(ValueError, match="exceeds evidence size"):
            c.validate(100)

    def test_data_length_mismatch(self):
        c = Chunk(index=0, offset=0, length=4, data=b"ab")
        with pytest.raises(ValueError, match="data length"):
            c.validate(100)

    def test_valid_chunk_passes(self):
        c = Chunk(index=0, offset=0, length=4, data=b"abcd")
        c.validate(100)  # Should not raise.


# ── 16. Default chunk size is 4096 ───────────────────────────────────

def test_default_chunk_size():
    assert DEFAULT_CHUNK_SIZE == 4096


# ── 17. Single-byte evidence ────────────────────────────────────────

def test_single_byte_evidence():
    data = b"\x42"
    chunks = chunk_evidence(data)

    assert len(chunks) == 1
    assert chunks[0].index == 0
    assert chunks[0].offset == 0
    assert chunks[0].length == 1
    assert chunks[0].data == b"\x42"

    meta = compute_metadata(data, "one.img")
    assert meta.size_bytes == 1
    assert meta.num_chunks == 1


# ── 18. Chunk size equals data size ──────────────────────────────────

def test_chunk_size_equals_data_size():
    data = b"EXACT" * 100  # 500 bytes
    chunks = chunk_evidence(data, chunk_size=500)
    assert len(chunks) == 1
    assert chunks[0].data == data


# ── 19. Chunk size larger than data ──────────────────────────────────

def test_chunk_size_larger_than_data():
    data = b"SMALL"  # 5 bytes
    chunks = chunk_evidence(data, chunk_size=4096)
    assert len(chunks) == 1
    assert chunks[0].length == 5
    assert chunks[0].data == data


# ── 20. Integration: reader → metadata → chunker ────────────────────

def test_full_pipeline(tmp_path):
    """End-to-end: read → compute metadata → chunk → reassemble."""
    content = bytes(range(256)) * 40  # 10,240 bytes
    img = _write_file(tmp_path / "pipeline.img", content)

    reader = EvidenceReader(img)
    meta = compute_metadata(reader.data, reader.filename)
    chunks = chunk_evidence(reader.data, meta.chunk_size)

    # Metadata correctness.
    assert meta.filename == "pipeline.img"
    assert meta.size_bytes == 10240
    assert meta.sha256 == hashlib.sha256(content).hexdigest()
    assert meta.chunk_size == DEFAULT_CHUNK_SIZE
    assert meta.num_chunks == math.ceil(10240 / DEFAULT_CHUNK_SIZE)

    # Chunk count matches metadata.
    assert len(chunks) == meta.num_chunks

    # Reassembled bytes match original.
    reassembled = b"".join(c.data for c in chunks)
    assert reassembled == content

    # Every chunk validates.
    for c in chunks:
        c.validate(meta.size_bytes)


# ── 21. Metadata frozen ─────────────────────────────────────────────

def test_metadata_is_frozen():
    meta = compute_metadata(b"data", "f.img")
    with pytest.raises(AttributeError):
        meta.filename = "changed.img"  # type: ignore[misc]


# ── 22. Chunk frozen ────────────────────────────────────────────────

def test_chunk_is_frozen():
    c = Chunk(index=0, offset=0, length=3, data=b"abc")
    with pytest.raises(AttributeError):
        c.index = 99  # type: ignore[misc]


# ── 23. Public API re-exports ───────────────────────────────────────

def test_public_api_reexports():
    """Verify the package __init__.py exports the correct names."""
    from backend.app import ingestion

    assert hasattr(ingestion, "EvidenceReader")
    assert hasattr(ingestion, "EvidenceMetadata")
    assert hasattr(ingestion, "compute_metadata")
    assert hasattr(ingestion, "Chunk")
    assert hasattr(ingestion, "chunk_evidence")
