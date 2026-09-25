"""
test_generator.py — Tests for the Recoverix synthetic evidence generator.

Covers: image creation, ground-truth manifest, determinism, scenario
validation, bounds checking, SHA-256 consistency, and error paths.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

import pytest
import sys

# Ensure imports work from the project root.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.app.generator.disk import EvidenceDisk, MAX_EVIDENCE_SIZE
from backend.app.generator.corruption import corrupt_region, CorruptionType
from backend.app.generator.ground_truth import (
    ArtifactEntry,
    BifragmentDescriptor,
    CorruptionDescriptor,
    FragmentDescriptor,
    GroundTruthManifest,
)
from backend.generate_case import generate_evidence, EVIDENCE_SIZE


# ── Helpers ─────────────────────────────────────────────────────────

SEED = 42
REQUIRED_SCENARIOS = {"clean", "deleted", "fragmented", "bifragment", "corrupted", "unrecoverable"}


@pytest.fixture(scope="module")
def generated_case(tmp_path_factory):
    """Run the generator once for the whole module and return the summary + paths."""
    out = tmp_path_factory.mktemp("evidence")
    summary = generate_evidence(SEED, out)
    return {
        "summary": summary,
        "output_dir": out,
        "img_path": out / "damaged.img",
        "manifest_path": out / "ground_truth.json",
    }


# ── 1. Generator creates evidence image ────────────────────────────

def test_evidence_image_created(generated_case):
    assert generated_case["img_path"].exists(), "damaged.img was not created"
    assert generated_case["img_path"].stat().st_size > 0, "damaged.img is empty"


# ── 2. Generator creates ground_truth.json ─────────────────────────

def test_manifest_created(generated_case):
    assert generated_case["manifest_path"].exists(), "ground_truth.json was not created"
    data = json.loads(generated_case["manifest_path"].read_text())
    assert "schema_version" in data
    assert "evidence" in data
    assert "artifacts" in data


# ── 3. Evidence size stays under 5 MiB ─────────────────────────────

def test_evidence_size_under_limit(generated_case):
    size = generated_case["img_path"].stat().st_size
    assert size <= MAX_EVIDENCE_SIZE, (
        f"Evidence {size} bytes exceeds {MAX_EVIDENCE_SIZE} byte limit"
    )


# ── 4. Same seed produces deterministic results ────────────────────

def test_determinism(tmp_path):
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"
    s1 = generate_evidence(SEED, out1)
    s2 = generate_evidence(SEED, out2)

    assert s1["evidence_sha256"] == s2["evidence_sha256"], "SHA-256 mismatch between runs"

    img1 = (out1 / "damaged.img").read_bytes()
    img2 = (out2 / "damaged.img").read_bytes()
    assert img1 == img2, "Image bytes differ between runs with same seed"

    manifest1 = json.loads((out1 / "ground_truth.json").read_text())
    manifest2 = json.loads((out2 / "ground_truth.json").read_text())
    assert manifest1 == manifest2, "Manifest differs between runs with same seed"


# ── 5. All six required scenarios exist ─────────────────────────────

def test_all_scenarios_present(generated_case):
    data = json.loads(generated_case["manifest_path"].read_text())
    scenarios = {a["scenario"] for a in data["artifacts"]}
    missing = REQUIRED_SCENARIOS - scenarios
    assert not missing, f"Missing scenarios: {missing}"


# ── 6. Manifest is valid and internally consistent ─────────────────

def test_manifest_valid(generated_case):
    data = json.loads(generated_case["manifest_path"].read_text())

    assert data["seed"] == SEED
    assert data["evidence"]["size_bytes"] == EVIDENCE_SIZE
    assert data["evidence"]["filename"] == "damaged.img"

    # Each artifact has required fields.
    for art in data["artifacts"]:
        assert "id" in art
        assert "filename" in art
        assert "format" in art
        assert "scenario" in art
        assert "original_size_bytes" in art
        assert isinstance(art["expected_recoverability"], bool)
        assert "fragments" in art
        assert isinstance(art["fragments"], list)


# ── 7. Every recorded fragment is inside evidence bounds ────────────

def test_fragments_in_bounds(generated_case):
    data = json.loads(generated_case["manifest_path"].read_text())
    image_size = data["evidence"]["size_bytes"]

    for art in data["artifacts"]:
        for frag in art["fragments"]:
            assert frag["offset"] >= 0, f"Negative offset in {art['id']}"
            assert frag["length"] > 0, f"Non-positive length in {art['id']}"
            end = frag["offset"] + frag["length"]
            assert end <= image_size, (
                f"Fragment in {art['id']} ends at {end}, image size is {image_size}"
            )


# ── 8. Bifragment gap is within 1..4096 bytes ──────────────────────

def test_bifragment_gap(generated_case):
    data = json.loads(generated_case["manifest_path"].read_text())
    bifrag_arts = [a for a in data["artifacts"] if a["scenario"] == "bifragment"]
    assert len(bifrag_arts) >= 1, "No bifragment scenario found"

    for art in bifrag_arts:
        assert "bifragment" in art and art["bifragment"] is not None
        gap = art["bifragment"]["gap_size"]
        assert 1 <= gap <= 4096, f"Gap {gap} outside [1, 4096]"
        assert art["bifragment"]["original_artifact_size"] == art["original_size_bytes"]


# ── 9. Corruption metadata is valid ────────────────────────────────

def test_corruption_metadata(generated_case):
    data = json.loads(generated_case["manifest_path"].read_text())
    corrupted_arts = [a for a in data["artifacts"] if a["scenario"] == "corrupted"]
    assert len(corrupted_arts) >= 1, "No corrupted scenario found"

    for art in corrupted_arts:
        assert "corruption" in art and art["corruption"] is not None
        c = art["corruption"]
        assert c["offset_within_artifact"] >= 0
        assert c["length"] > 0
        assert c["offset_within_artifact"] + c["length"] <= art["original_size_bytes"]
        assert c["corruption_type"] in {"zero_fill", "random_overwrite", "bit_flip"}
        assert "description" in c and len(c["description"]) > 0


# ── 10. Unrecoverable case is marked unrecoverable ──────────────────

def test_unrecoverable_marked(generated_case):
    data = json.loads(generated_case["manifest_path"].read_text())
    unrec_arts = [a for a in data["artifacts"] if a["scenario"] == "unrecoverable"]
    assert len(unrec_arts) >= 1, "No unrecoverable scenario found"

    for art in unrec_arts:
        assert art["expected_recoverability"] is False, (
            f"Unrecoverable artifact {art['id']} has expected_recoverability=True"
        )


# ── 11. Evidence SHA-256 matches manifest ───────────────────────────

def test_sha256_consistency(generated_case):
    data = json.loads(generated_case["manifest_path"].read_text())
    img_bytes = generated_case["img_path"].read_bytes()
    computed = hashlib.sha256(img_bytes).hexdigest()
    assert computed == data["evidence"]["sha256"], (
        f"SHA-256 mismatch: computed {computed}, manifest says {data['evidence']['sha256']}"
    )


# ── 12. Generator rejects invalid configuration ────────────────────

class TestDiskValidation:
    def test_zero_size(self):
        with pytest.raises(ValueError, match="positive"):
            EvidenceDisk(0)

    def test_negative_size(self):
        with pytest.raises(ValueError, match="positive"):
            EvidenceDisk(-1)

    def test_exceeds_limit(self):
        with pytest.raises(ValueError, match="exceeds hard limit"):
            EvidenceDisk(MAX_EVIDENCE_SIZE + 1)

    def test_invalid_fill(self):
        with pytest.raises(ValueError):
            EvidenceDisk(1024, fill=0x100)

    def test_write_oob(self):
        disk = EvidenceDisk(1024)
        with pytest.raises(ValueError, match="exceeds image size"):
            disk.write(1020, b"\xff" * 10)

    def test_write_negative_offset(self):
        disk = EvidenceDisk(1024)
        with pytest.raises(ValueError, match="Negative offset"):
            disk.write(-1, b"\xff")

    def test_read_oob(self):
        disk = EvidenceDisk(1024)
        with pytest.raises(ValueError, match="exceeds image size"):
            disk.read(1020, 10)

    def test_read_negative(self):
        disk = EvidenceDisk(1024)
        with pytest.raises(ValueError, match="Negative offset"):
            disk.read(-1, 10)


class TestCorruptionValidation:
    def test_negative_offset(self):
        import random
        rng = random.Random(0)
        with pytest.raises(ValueError, match="non-negative"):
            corrupt_region(b"hello", -1, 2, CorruptionType.ZERO_FILL, rng)

    def test_zero_length(self):
        import random
        rng = random.Random(0)
        with pytest.raises(ValueError, match="positive"):
            corrupt_region(b"hello", 0, 0, CorruptionType.ZERO_FILL, rng)

    def test_oob(self):
        import random
        rng = random.Random(0)
        with pytest.raises(ValueError, match="exceeds artifact size"):
            corrupt_region(b"hello", 3, 5, CorruptionType.ZERO_FILL, rng)


class TestManifestValidation:
    def test_duplicate_ids(self):
        m = GroundTruthManifest(
            seed=0, evidence_filename="x.img",
            evidence_size_bytes=1024, evidence_sha256="abc",
        )
        entry = ArtifactEntry(
            id="dup", filename="a.txt", format="txt", scenario="clean",
            original_size_bytes=10, expected_recoverability=True,
            fragments=[FragmentDescriptor(0, 0, 10)],
        )
        m.add(entry)
        m.add(ArtifactEntry(
            id="dup", filename="b.txt", format="txt", scenario="clean",
            original_size_bytes=10, expected_recoverability=True,
            fragments=[FragmentDescriptor(0, 100, 10)],
        ))
        with pytest.raises(ValueError, match="Duplicate artifact id"):
            m.validate()

    def test_fragment_oob(self):
        m = GroundTruthManifest(
            seed=0, evidence_filename="x.img",
            evidence_size_bytes=100, evidence_sha256="abc",
        )
        m.add(ArtifactEntry(
            id="oob", filename="a.txt", format="txt", scenario="clean",
            original_size_bytes=50, expected_recoverability=True,
            fragments=[FragmentDescriptor(0, 90, 20)],  # ends at 110 > 100
        ))
        with pytest.raises(ValueError, match="exceeds image size"):
            m.validate()

    def test_bifragment_gap_too_large(self):
        entry = ArtifactEntry(
            id="bg", filename="a.txt", format="txt", scenario="bifragment",
            original_size_bytes=100, expected_recoverability=True,
            fragments=[
                FragmentDescriptor(0, 0, 50),
                FragmentDescriptor(1, 100, 50),
            ],
            bifragment=BifragmentDescriptor(
                fragment_a_index=0, fragment_b_index=1,
                gap_size=5000,  # > 4096
                original_artifact_size=100,
            ),
        )
        m = GroundTruthManifest(
            seed=0, evidence_filename="x.img",
            evidence_size_bytes=200, evidence_sha256="abc",
        )
        m.add(entry)
        with pytest.raises(ValueError, match="gap"):
            m.validate()


# ── Corruption unit tests ──────────────────────────────────────────

class TestCorruptionTypes:
    def test_zero_fill(self):
        import random
        data = b"ABCDEFGHIJ"
        rng = random.Random(99)
        result, rec = corrupt_region(data, 2, 4, CorruptionType.ZERO_FILL, rng)
        assert result[2:6] == b"\x00\x00\x00\x00"
        assert result[:2] == b"AB"
        assert result[6:] == b"GHIJ"
        assert rec.corruption_type == "zero_fill"

    def test_random_overwrite(self):
        import random
        data = b"ABCDEFGHIJ"
        rng = random.Random(99)
        result, rec = corrupt_region(data, 0, 3, CorruptionType.RANDOM_OVERWRITE, rng)
        assert result[:3] != b"ABC"
        assert result[3:] == b"DEFGHIJ"
        assert rec.corruption_type == "random_overwrite"

    def test_bit_flip(self):
        import random
        data = b"\xff\xff\xff"
        rng = random.Random(99)
        result, rec = corrupt_region(data, 0, 3, CorruptionType.BIT_FLIP, rng)
        # At least one byte should differ.
        assert result != bytearray(data)
        assert rec.corruption_type == "bit_flip"

    def test_corruption_determinism(self):
        import random
        data = b"0123456789"
        r1, _ = corrupt_region(data, 1, 5, CorruptionType.RANDOM_OVERWRITE, random.Random(7))
        r2, _ = corrupt_region(data, 1, 5, CorruptionType.RANDOM_OVERWRITE, random.Random(7))
        assert r1 == r2


# ── Disk unit tests ─────────────────────────────────────────────────

class TestDiskUnit:
    def test_write_read_roundtrip(self):
        disk = EvidenceDisk(256)
        disk.write(10, b"HELLO")
        assert disk.read(10, 5) == b"HELLO"

    def test_sha256_determinism(self):
        d1 = EvidenceDisk(512, fill=0xAA)
        d2 = EvidenceDisk(512, fill=0xAA)
        assert d1.sha256() == d2.sha256()

    def test_save_roundtrip(self, tmp_path):
        disk = EvidenceDisk(128, fill=0xBB)
        disk.write(0, b"XYZ")
        path = disk.save(tmp_path / "sub" / "test.img")
        assert path.exists()
        content = path.read_bytes()
        assert content[:3] == b"XYZ"
        assert content[3] == 0xBB
        assert len(content) == 128


# ── Different seeds produce different output ────────────────────────

def test_different_seeds_differ(tmp_path):
    s1 = generate_evidence(42, tmp_path / "a")
    s2 = generate_evidence(99, tmp_path / "b")
    assert s1["evidence_sha256"] != s2["evidence_sha256"]
