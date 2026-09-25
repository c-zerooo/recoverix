"""
ground_truth.py — Ground-truth manifest builder.

Collects artifact metadata as the generator lays out evidence and
serialises it to a validated JSON manifest.  The manifest is the
single source of truth for automated testing of the recovery engine.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "1.0.0"


# ── fragment / corruption / bifragment descriptors ──────────────────

@dataclass
class FragmentDescriptor:
    """Positional descriptor for one contiguous fragment in the image."""

    fragment_index: int
    offset: int
    length: int

    def validate(self, image_size: int) -> None:
        """Raise ValueError if this fragment is out of bounds."""
        if self.offset < 0:
            raise ValueError(f"Fragment {self.fragment_index}: negative offset {self.offset}")
        if self.length <= 0:
            raise ValueError(f"Fragment {self.fragment_index}: non-positive length {self.length}")
        end = self.offset + self.length
        if end > image_size:
            raise ValueError(
                f"Fragment {self.fragment_index}: end {end} exceeds image size {image_size}"
            )


@dataclass
class CorruptionDescriptor:
    """Records a single corruption operation applied to an artifact."""

    corruption_type: str
    offset_within_artifact: int
    length: int
    description: str


@dataclass
class BifragmentDescriptor:
    """Records bifragment layout: two fragments with a gap between."""

    fragment_a_index: int
    fragment_b_index: int
    gap_size: int
    original_artifact_size: int

    # Maximum gap the future recovery engine will search.
    MAX_GAP: int = 4096

    def validate(self) -> None:
        if not (1 <= self.gap_size <= self.MAX_GAP):
            raise ValueError(
                f"Bifragment gap {self.gap_size} outside allowed range "
                f"[1, {self.MAX_GAP}]"
            )


# ── per-artifact entry ──────────────────────────────────────────────

@dataclass
class ArtifactEntry:
    """Ground-truth record for a single synthetic artifact."""

    id: str
    filename: str
    format: str
    scenario: str
    original_size_bytes: int
    expected_recoverability: bool
    fragments: List[FragmentDescriptor] = field(default_factory=list)
    corruption: Optional[CorruptionDescriptor] = None
    bifragment: Optional[BifragmentDescriptor] = None
    notes: Optional[str] = None

    def validate(self, image_size: int) -> None:
        """Run structural validations against the image geometry."""
        if self.original_size_bytes <= 0:
            raise ValueError(f"Artifact {self.id}: non-positive original_size_bytes")

        for frag in self.fragments:
            frag.validate(image_size)

        if self.bifragment is not None:
            self.bifragment.validate()

        # Validate corruption descriptor bounds against artifact size.
        if self.corruption is not None:
            c = self.corruption
            if c.offset_within_artifact < 0:
                raise ValueError(f"Artifact {self.id}: negative corruption offset")
            if c.length <= 0:
                raise ValueError(f"Artifact {self.id}: non-positive corruption length")
            if c.offset_within_artifact + c.length > self.original_size_bytes:
                raise ValueError(
                    f"Artifact {self.id}: corruption region exceeds artifact size"
                )

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a JSON-safe dictionary."""
        d: Dict[str, Any] = {
            "id": self.id,
            "filename": self.filename,
            "format": self.format,
            "scenario": self.scenario,
            "original_size_bytes": self.original_size_bytes,
            "expected_recoverability": self.expected_recoverability,
            "fragments": [asdict(f) for f in self.fragments],
        }
        if self.corruption is not None:
            d["corruption"] = asdict(self.corruption)
        if self.bifragment is not None:
            d["bifragment"] = {
                "fragment_a_index": self.bifragment.fragment_a_index,
                "fragment_b_index": self.bifragment.fragment_b_index,
                "gap_size": self.bifragment.gap_size,
                "original_artifact_size": self.bifragment.original_artifact_size,
            }
        if self.notes is not None:
            d["notes"] = self.notes
        return d


# ── manifest ────────────────────────────────────────────────────────

@dataclass
class GroundTruthManifest:
    """Top-level ground-truth document."""

    seed: int
    evidence_filename: str
    evidence_size_bytes: int
    evidence_sha256: str
    artifacts: List[ArtifactEntry] = field(default_factory=list)

    def add(self, entry: ArtifactEntry) -> None:
        self.artifacts.append(entry)

    def validate(self) -> None:
        """Validate the entire manifest for internal consistency."""
        if self.evidence_size_bytes <= 0:
            raise ValueError("Evidence size must be positive")

        seen_ids: set[str] = set()
        for art in self.artifacts:
            if art.id in seen_ids:
                raise ValueError(f"Duplicate artifact id: {art.id}")
            seen_ids.add(art.id)
            art.validate(self.evidence_size_bytes)

        # Check that no two fragments from different artifacts overlap
        # (unless one is the unrecoverable/overwritten region by design).
        occupied: List[tuple[int, int, str]] = []
        for art in self.artifacts:
            for frag in art.fragments:
                occupied.append((frag.offset, frag.offset + frag.length, art.id))

        occupied.sort()
        for i in range(len(occupied) - 1):
            _, end_a, id_a = occupied[i]
            start_b, _, id_b = occupied[i + 1]
            if end_a > start_b and id_a != id_b:
                raise ValueError(
                    f"Overlapping fragments between artifact {id_a} and {id_b} "
                    f"(end {end_a} > start {start_b})"
                )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "seed": self.seed,
            "evidence": {
                "filename": self.evidence_filename,
                "size_bytes": self.evidence_size_bytes,
                "sha256": self.evidence_sha256,
            },
            "artifacts": [a.to_dict() for a in self.artifacts],
        }

    def save(self, path: Path | str) -> Path:
        """Write the manifest to *path* as formatted JSON.

        Validates before writing — will raise on inconsistency.
        """
        self.validate()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n")
        return path.resolve()
