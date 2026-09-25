#!/usr/bin/env python3
"""
generate_case.py — Recoverix synthetic evidence generator.

Usage:
    python backend/generate_case.py --seed 42
    python backend/generate_case.py --seed 42 --output-dir backend/generated

Produces:
    <output-dir>/damaged.img        — synthetic evidence image
    <output-dir>/ground_truth.json  — machine-readable manifest

This script creates controlled forensic test data with six required
scenarios: clean, deleted, fragmented, bifragment, corrupted, and
unrecoverable.  Every byte placement is deterministic given the seed.

NOTE ON SYNTHETIC BOUNDARY MARKERS
-----------------------------------
TXT and CSV artifacts use [SYNTHETIC_ARTIFACT_START] / [SYNTHETIC_ARTIFACT_END]
markers.  These are ONLY meaningful inside this test harness.  They are NOT a
claim that arbitrary plaintext files can be carved using such markers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

# Ensure the project root is importable.
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

# ── constants ───────────────────────────────────────────────────────

EVIDENCE_SIZE: int = 1 * 1024 * 1024  # 1 MiB — well under the 5 MiB limit
EVIDENCE_FILENAME: str = "damaged.img"
MANIFEST_FILENAME: str = "ground_truth.json"
DEFAULT_OUTPUT_DIR: str = "backend/generated"

# Fill byte for unused regions; 0x00 mimics zeroed disk blocks.
FILL_BYTE: int = 0x00

# Future recovery engine constant — used only for gap-size generation.
MAX_GAP: int = 4096

# Alignment for artifact placement — keeps layout clean.
SECTOR: int = 512


def _align(offset: int, alignment: int = SECTOR) -> int:
    """Round *offset* up to the next multiple of *alignment*."""
    remainder = offset % alignment
    return offset if remainder == 0 else offset + (alignment - remainder)


# ── Synthetic artifact builders ─────────────────────────────────────

def _make_txt(name: str, body_lines: list[str]) -> bytes:
    """Build a synthetic TXT artifact with boundary markers.

    NOTE: The [SYNTHETIC_ARTIFACT_START/END] markers exist ONLY for this
    test harness.  They do NOT represent a general plaintext carving strategy.
    """
    lines = [
        "[SYNTHETIC_ARTIFACT_START]",
        f"filename: {name}",
        *body_lines,
        "[SYNTHETIC_ARTIFACT_END]",
    ]
    return "\n".join(lines).encode("utf-8")


def _make_csv(name: str, rows: list[list[str]]) -> bytes:
    """Build a synthetic CSV artifact with boundary markers.

    NOTE: See _make_txt — same caveat about synthetic markers.
    """
    lines = ["[SYNTHETIC_ARTIFACT_START]"]
    for row in rows:
        lines.append(",".join(row))
    lines.append("[SYNTHETIC_ARTIFACT_END]")
    return "\n".join(lines).encode("utf-8")


def _make_binary_blob(rng: random.Random, size: int) -> bytes:
    """Generate a deterministic pseudo-random binary blob."""
    return bytes(rng.randint(0, 255) for _ in range(size))


# ── Scenario builders ──────────────────────────────────────────────

def _scenario_clean(
    disk: EvidenceDisk,
    manifest: GroundTruthManifest,
    offset: int,
) -> int:
    """Scenario 1 — CLEAN / CONTIGUOUS: a fully intact artifact."""
    payload = _make_txt(
        "evidence_log.txt",
        [
            "type: access_log",
            "timestamp: 2025-03-15T08:30:00Z",
            "user: admin",
            "action: login",
            "ip: 192.168.1.100",
            "status: success",
        ],
    )
    disk.write(offset, payload)
    manifest.add(ArtifactEntry(
        id="art-clean-01",
        filename="evidence_log.txt",
        format="txt",
        scenario="clean",
        original_size_bytes=len(payload),
        expected_recoverability=True,
        fragments=[FragmentDescriptor(fragment_index=0, offset=offset, length=len(payload))],
    ))
    return offset + len(payload)


def _scenario_deleted(
    disk: EvidenceDisk,
    manifest: GroundTruthManifest,
    offset: int,
) -> int:
    """Scenario 2 — DELETED: bytes present, but no filesystem metadata.

    The data is written to the image (so the future carver can find it),
    but the ground truth marks it as 'deleted' — meaning no directory
    entry or allocation table points to it in our synthetic model.
    """
    payload = _make_csv(
        "deleted_transactions.csv",
        [
            ["txn_id", "date", "amount", "account"],
            ["T1001", "2025-01-10", "5000.00", "ACC-4421"],
            ["T1002", "2025-01-11", "12300.50", "ACC-4421"],
            ["T1003", "2025-01-12", "780.25", "ACC-9983"],
            ["T1004", "2025-01-13", "44100.00", "ACC-4421"],
        ],
    )
    disk.write(offset, payload)
    manifest.add(ArtifactEntry(
        id="art-deleted-01",
        filename="deleted_transactions.csv",
        format="csv",
        scenario="deleted",
        original_size_bytes=len(payload),
        expected_recoverability=True,
        fragments=[FragmentDescriptor(fragment_index=0, offset=offset, length=len(payload))],
        notes="Bytes present in image; no synthetic filesystem metadata points here.",
    ))
    return offset + len(payload)


def _scenario_fragmented(
    disk: EvidenceDisk,
    manifest: GroundTruthManifest,
    rng: random.Random,
    frag_offsets: list[int],
) -> int:
    """Scenario 3 — FRAGMENTED: artifact split into 3 non-contiguous fragments.

    *frag_offsets* gives the start position for each fragment.
    Returns the end of the last fragment written.
    """
    full_payload = _make_txt(
        "fragmented_report.txt",
        [
            "type: incident_report",
            "case: IR-2025-0042",
            "severity: high",
            "summary: Unauthorized access detected on internal file server.",
            "affected_hosts: srv-file-01, srv-file-02",
            "timeline: Initial access at 02:14 UTC, lateral movement at 02:31 UTC.",
            "containment: Network segment isolated at 03:05 UTC.",
            "status: under_investigation",
        ],
    )

    num_frags = 3
    base_size = len(full_payload) // num_frags
    # Distribute remainder to the last fragment.
    frag_sizes = [base_size] * num_frags
    frag_sizes[-1] += len(full_payload) - base_size * num_frags

    if len(frag_offsets) != num_frags:
        raise ValueError(f"Expected {num_frags} fragment offsets, got {len(frag_offsets)}")

    fragments: list[FragmentDescriptor] = []
    data_cursor = 0
    last_end = 0
    for idx, (off, size) in enumerate(zip(frag_offsets, frag_sizes)):
        chunk = full_payload[data_cursor : data_cursor + size]
        disk.write(off, chunk)
        fragments.append(FragmentDescriptor(fragment_index=idx, offset=off, length=size))
        data_cursor += size
        last_end = max(last_end, off + size)

    manifest.add(ArtifactEntry(
        id="art-fragmented-01",
        filename="fragmented_report.txt",
        format="txt",
        scenario="fragmented",
        original_size_bytes=len(full_payload),
        expected_recoverability=True,
        fragments=fragments,
        notes="Artifact split into 3 non-contiguous fragments placed at known offsets.",
    ))
    return last_end


def _scenario_bifragment(
    disk: EvidenceDisk,
    manifest: GroundTruthManifest,
    rng: random.Random,
    offset_a: int,
    offset_b: int,
    gap_size: int,
) -> int:
    """Scenario 4 — BIFRAGMENT: two fragments with a gap in between.

    Fragment A is written at *offset_a*, Fragment B at *offset_b*.
    The gap between them (on the image) is filled with unrelated noise
    to simulate real-world interleaving.

    The *gap_size* is the number of unknown bytes the future engine
    will need to account for when attempting reconstruction.
    """
    full_payload = _make_txt(
        "bifragment_memo.txt",
        [
            "type: internal_memo",
            "subject: Credentials rotation schedule",
            "from: security-team@example.com",
            "to: all-staff@example.com",
            "body: All service account credentials must be rotated by EOD Friday.",
            "priority: urgent",
        ],
    )

    split_point = len(full_payload) // 2
    frag_a = full_payload[:split_point]
    frag_b = full_payload[split_point:]

    disk.write(offset_a, frag_a)
    disk.write(offset_b, frag_b)

    # Fill the gap region (between A end and B start on the image) with noise.
    gap_start = offset_a + len(frag_a)
    noise = bytes(rng.randint(0, 255) for _ in range(gap_size))
    disk.write(gap_start, noise)

    manifest.add(ArtifactEntry(
        id="art-bifragment-01",
        filename="bifragment_memo.txt",
        format="txt",
        scenario="bifragment",
        original_size_bytes=len(full_payload),
        expected_recoverability=True,
        fragments=[
            FragmentDescriptor(fragment_index=0, offset=offset_a, length=len(frag_a)),
            FragmentDescriptor(fragment_index=1, offset=offset_b, length=len(frag_b)),
        ],
        bifragment=BifragmentDescriptor(
            fragment_a_index=0,
            fragment_b_index=1,
            gap_size=gap_size,
            original_artifact_size=len(full_payload),
        ),
        notes=(
            f"Fragment A + {gap_size}-byte gap + Fragment B.  "
            "Future engine must search gap range [1, 4096] to reconstruct."
        ),
    ))
    return max(offset_a + len(frag_a) + gap_size, offset_b + len(frag_b))


def _scenario_corrupted(
    disk: EvidenceDisk,
    manifest: GroundTruthManifest,
    rng: random.Random,
    offset: int,
) -> int:
    """Scenario 5 — CORRUPTED: artifact with deterministic byte damage."""
    payload = _make_txt(
        "corrupted_config.txt",
        [
            "type: server_config",
            "hostname: db-primary-01",
            "port: 5432",
            "max_connections: 200",
            "ssl_mode: verify-full",
            "data_directory: /var/lib/postgresql/15/main",
            "log_level: warning",
        ],
    )

    # Corrupt a region in the middle of the artifact.
    corrupt_offset = len(payload) // 4
    corrupt_length = min(32, len(payload) // 4)

    corrupted_data, record = corrupt_region(
        payload, corrupt_offset, corrupt_length, CorruptionType.RANDOM_OVERWRITE, rng
    )

    disk.write(offset, bytes(corrupted_data))

    manifest.add(ArtifactEntry(
        id="art-corrupted-01",
        filename="corrupted_config.txt",
        format="txt",
        scenario="corrupted",
        original_size_bytes=len(payload),
        expected_recoverability=True,
        fragments=[FragmentDescriptor(fragment_index=0, offset=offset, length=len(payload))],
        corruption=CorruptionDescriptor(
            corruption_type=record.corruption_type,
            offset_within_artifact=record.offset_within_artifact,
            length=record.length,
            description=record.description,
        ),
        notes="Partial corruption; artifact may be partially recoverable.",
    ))
    return offset + len(payload)


def _scenario_unrecoverable(
    disk: EvidenceDisk,
    manifest: GroundTruthManifest,
    rng: random.Random,
    offset: int,
) -> int:
    """Scenario 6 — UNRECOVERABLE: artifact that cannot be reconstructed.

    We write only a small fragment of the original artifact and overwrite
    the rest with unrelated data, making full recovery impossible.
    """
    full_payload = _make_txt(
        "destroyed_evidence.txt",
        [
            "type: key_material",
            "algorithm: AES-256-GCM",
            "key_id: KEY-2025-ALPHA",
            "created: 2025-02-20T14:00:00Z",
            "NOTE: This key material has been destroyed and cannot be recovered.",
        ],
    )

    # Write only the first 20% — the rest is gone.
    surviving_length = max(16, len(full_payload) // 5)
    surviving_data = full_payload[:surviving_length]
    disk.write(offset, surviving_data)

    # Overwrite the rest of the region with noise so nothing useful remains.
    destroyed_length = len(full_payload) - surviving_length
    noise = bytes(rng.randint(0, 255) for _ in range(destroyed_length))
    disk.write(offset + surviving_length, noise)

    manifest.add(ArtifactEntry(
        id="art-unrecoverable-01",
        filename="destroyed_evidence.txt",
        format="txt",
        scenario="unrecoverable",
        original_size_bytes=len(full_payload),
        expected_recoverability=False,
        fragments=[
            FragmentDescriptor(
                fragment_index=0, offset=offset, length=surviving_length
            ),
        ],
        notes=(
            f"Only {surviving_length} of {len(full_payload)} bytes survive.  "
            f"Remaining {destroyed_length} bytes overwritten with random noise."
        ),
    ))
    return offset + len(full_payload)


# ── Orchestrator ────────────────────────────────────────────────────

def generate_evidence(seed: int, output_dir: Path) -> dict:
    """Generate the complete synthetic evidence case.

    Args:
        seed: Deterministic seed for all random operations.
        output_dir: Directory for damaged.img and ground_truth.json.

    Returns:
        A summary dict (for programmatic use and reporting).

    Raises:
        ValueError: If any safety invariant is violated.
    """
    rng = random.Random(seed)

    if EVIDENCE_SIZE > MAX_EVIDENCE_SIZE:
        raise ValueError(
            f"Configured evidence size {EVIDENCE_SIZE} exceeds limit {MAX_EVIDENCE_SIZE}"
        )

    disk = EvidenceDisk(EVIDENCE_SIZE, fill=FILL_BYTE)

    # Placeholder manifest — sha256 is filled in after all writes.
    manifest = GroundTruthManifest(
        seed=seed,
        evidence_filename=EVIDENCE_FILENAME,
        evidence_size_bytes=EVIDENCE_SIZE,
        evidence_sha256="",  # filled in after all writes
    )

    # ── Layout plan ─────────────────────────────────────────────
    # We place artifacts at sector-aligned offsets with gaps between
    # them.  The fragmented artifact is split across three separated
    # positions.  The bifragment artifact uses a contiguous A+gap+B
    # layout at a known position.
    #
    # Approximate layout (1 MiB = 1048576 bytes):
    #
    # 0x00000  …  clean artifact
    # 0x10000  …  deleted artifact
    # 0x20000  …  fragmented fragment 0
    # 0x30000  …  fragmented fragment 1
    # 0x40000  …  fragmented fragment 2
    # 0x50000  …  bifragment (A + gap + B placed contiguously)
    # 0x70000  …  corrupted artifact
    # 0x80000  …  unrecoverable artifact
    #
    # All offsets are well within the 1 MiB image.

    cursor = _align(0x00000)
    cursor = _scenario_clean(disk, manifest, cursor)

    cursor = _align(0x10000)
    cursor = _scenario_deleted(disk, manifest, cursor)

    # Fragmented — three non-contiguous regions.
    frag_offsets = [_align(0x20000), _align(0x30000), _align(0x40000)]
    cursor = _scenario_fragmented(disk, manifest, rng, frag_offsets)

    # Bifragment — A placed, then gap, then B immediately after gap.
    gap_size = rng.randint(128, MAX_GAP)  # within [1, 4096]
    bifrag_offset_a = _align(0x50000)
    # B starts right after A's data + gap on the image to keep the
    # layout simple and verifiable.
    # We need to know A's size to compute B's offset, so we peek at
    # the payload length.
    bifrag_payload = _make_txt(
        "bifragment_memo.txt",
        [
            "type: internal_memo",
            "subject: Credentials rotation schedule",
            "from: security-team@example.com",
            "to: all-staff@example.com",
            "body: All service account credentials must be rotated by EOD Friday.",
            "priority: urgent",
        ],
    )
    split_point = len(bifrag_payload) // 2
    bifrag_offset_b = bifrag_offset_a + split_point + gap_size
    cursor = _scenario_bifragment(
        disk, manifest, rng, bifrag_offset_a, bifrag_offset_b, gap_size
    )

    cursor = _align(0x70000)
    cursor = _scenario_corrupted(disk, manifest, rng, cursor)

    cursor = _align(0x80000)
    cursor = _scenario_unrecoverable(disk, manifest, rng, cursor)

    # ── Finalise ────────────────────────────────────────────────

    # Compute SHA-256 after all writes.
    manifest.evidence_sha256 = disk.sha256()

    # Validate the entire manifest before saving.
    manifest.validate()

    # Persist.
    img_path = disk.save(output_dir / EVIDENCE_FILENAME)
    manifest_path = manifest.save(output_dir / MANIFEST_FILENAME)

    # ── Post-write verification ─────────────────────────────────

    # Verify on-disk SHA-256 matches what we recorded.
    on_disk_hash = hashlib.sha256(img_path.read_bytes()).hexdigest()
    if on_disk_hash != manifest.evidence_sha256:
        raise RuntimeError(
            f"SHA-256 mismatch!  Expected {manifest.evidence_sha256}, "
            f"got {on_disk_hash}"
        )

    # Verify size.
    on_disk_size = img_path.stat().st_size
    if on_disk_size != EVIDENCE_SIZE:
        raise RuntimeError(
            f"Evidence size mismatch!  Expected {EVIDENCE_SIZE}, got {on_disk_size}"
        )

    return {
        "seed": seed,
        "evidence_path": str(img_path),
        "manifest_path": str(manifest_path),
        "evidence_size": on_disk_size,
        "evidence_sha256": on_disk_hash,
        "artifact_count": len(manifest.artifacts),
        "scenarios": [a.scenario for a in manifest.artifacts],
    }


# ── CLI ─────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recoverix synthetic evidence generator",
    )
    parser.add_argument(
        "--seed", type=int, required=True, help="Deterministic seed"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    print(f"Generating evidence with seed={args.seed} → {output_dir}/")

    summary = generate_evidence(args.seed, output_dir)

    print()
    print("═" * 60)
    print("  GENERATION COMPLETE")
    print("═" * 60)
    print(f"  Evidence : {summary['evidence_path']}")
    print(f"  Manifest : {summary['manifest_path']}")
    print(f"  Size     : {summary['evidence_size']:,} bytes")
    print(f"  SHA-256  : {summary['evidence_sha256']}")
    print(f"  Artifacts: {summary['artifact_count']}")
    print(f"  Scenarios: {', '.join(summary['scenarios'])}")
    print("═" * 60)


if __name__ == "__main__":
    main()
