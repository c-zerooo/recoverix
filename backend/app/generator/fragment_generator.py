"""Deterministic, ground-truthed TXT/CSV fragment and damage generation.

Unlike the legacy evidence-image test harness, this module emits the *present*
evidence bytes only. A physical gap is represented by the absence of the source
range from ``evidence_bytes``; it is never padded with spaces, zeroes, or noise.

The original source remains available on each :class:`FragmentCase` and can be
written beside the evidence and JSON manifest with :func:`write_fragment_case`.
No reconstruction is performed here.
"""

from __future__ import annotations

import base64
import hashlib
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

SUPPORTED_FORMATS = ("txt", "csv")
SUPPORTED_SCENARIOS = (
    "clean",
    "fragmented",
    "truncated",
    "corrupted",
    "unrecoverable",
)

# Ordinary, unmarked fixture content. Each record is realistic plain-language
# operational text or a conventional header-plus-record CSV file.
STANDARD_FIXTURES: Mapping[str, tuple[str, bytes]] = {
    "txt": (
        "incident_response_notes.txt",
        (
            b"Incident response notes\n"
            b"Case: IR-2026-0417\n"
            b"Opened: 2026-04-17T09:14:32Z\n"
            b"Analyst: Morgan Ellis\n"
            b"Source: workstation WS-184\n"
            b"Finding: repeated authentication failures preceded access.\n"
            b"Containment: account disabled and endpoint isolated.\n"
            b"Follow-up: preserve the disk image for independent review.\n"
        ),
    ),
    "csv": (
        "authentication_events.csv",
        (
            b"timestamp,host,user,event,result\n"
            b"2026-04-17T08:52:11Z,WS-184,mellis,login,failed\n"
            b"2026-04-17T08:53:02Z,WS-184,mellis,login,failed\n"
            b"2026-04-17T08:54:47Z,WS-184,mellis,login,success\n"
            b"2026-04-17T08:55:09Z,FS-02,mellis,share_access,allowed\n"
            b"2026-04-17T09:02:31Z,WS-184,mellis,process_start,blocked\n"
            b"2026-04-17T09:14:32Z,WS-184,mellis,account_lock,applied\n"
        ),
    ),
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_source(original_bytes: bytes, fmt: str, scenario: str) -> tuple[str, str]:
    if not isinstance(original_bytes, bytes):
        raise TypeError("original_bytes must be bytes")
    if not original_bytes:
        raise ValueError("original_bytes must not be empty")
    normalized_format = fmt.lower().lstrip(".")
    if normalized_format not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported format {fmt!r}; expected txt or csv")
    normalized_scenario = scenario.lower()
    if normalized_scenario not in SUPPORTED_SCENARIOS:
        raise ValueError(
            f"Unsupported scenario {scenario!r}; expected one of {SUPPORTED_SCENARIOS}"
        )
    return normalized_format, normalized_scenario


@dataclass(frozen=True)
class FragmentDescriptor:
    """One present byte run and its source-coordinate mapping."""

    fragment_index: int
    offset: int  # Offset in original-file coordinates.
    length: int
    sha256: str  # Hash of the bytes actually present in the evidence.
    evidence_offset: int  # Offset in the packed evidence byte stream.
    source_sha256: str  # Hash of the original source slice at ``offset``.

    @property
    def end_offset(self) -> int:
        return self.offset + self.length


@dataclass(frozen=True)
class FragmentCase:
    """A reproducible original/evidence pair with a verified ground-truth map."""

    case_id: str
    format: str
    scenario: str
    seed: int
    original_filename: str
    original_bytes: bytes = field(repr=False)
    evidence_bytes: bytes = field(repr=False)
    fragments: tuple[FragmentDescriptor, ...]
    gap_start: int
    gap_end: int
    missing_bytes: bytes = field(repr=False)
    damage_type: str
    corruption_start: int | None = None
    corruption_end: int | None = None

    @property
    def original_size(self) -> int:
        return len(self.original_bytes)

    @property
    def original_sha256(self) -> str:
        return _sha256(self.original_bytes)

    @property
    def evidence_size(self) -> int:
        return len(self.evidence_bytes)

    @property
    def evidence_sha256(self) -> str:
        return _sha256(self.evidence_bytes)

    @property
    def gap_length(self) -> int:
        return self.gap_end - self.gap_start

    @property
    def missing_sha256(self) -> str | None:
        return _sha256(self.missing_bytes) if self.missing_bytes else None

    @property
    def physical_gap(self) -> bool:
        return self.gap_length > 0

    @property
    def present_evidence_bytes(self) -> int:
        """Bytes physically present in the evidence, summed over all fragments."""
        return sum(f.length for f in self.fragments)

    @property
    def missing_byte_count(self) -> int:
        """Bytes of the original that are physically absent from the evidence."""
        return len(self.missing_bytes)

    @property
    def corrupted_byte_count(self) -> int:
        """Present bytes whose value diverges from the original at the same offset.

        Zero unless this is a corruption scenario. Corruption is *not* missing
        bytes: the byte positions are present in the evidence, but their contents
        no longer match the original.
        """
        if self.corruption_start is None or self.corruption_end is None:
            return 0
        start, end = self.corruption_start, self.corruption_end
        divergence = 0
        for frag in self.fragments:
            lo = max(frag.offset, start)
            hi = min(frag.end_offset, end)
            if lo >= hi:
                continue
            present = self.evidence_bytes[
                frag.evidence_offset + (lo - frag.offset) :
                frag.evidence_offset + (hi - frag.offset)
            ]
            divergence += sum(
                1
                for got, want in zip(present, self.original_bytes[lo:hi])
                if got != want
            )
        return divergence

    @property
    def missing_bytes_absent_from_evidence(self) -> bool:
        """True when the removed source range is genuinely not present anywhere.

        Checked twice: the fragment source-coordinate ranges must be disjoint from
        the gap range, and the gap payload must not appear in the evidence stream.
        """
        if not self.physical_gap:
            return True
        for frag in self.fragments:
            if frag.offset < self.gap_end and frag.end_offset > self.gap_start:
                return False
        if len(self.missing_bytes) >= 3:
            return self.evidence_bytes.find(self.missing_bytes) == -1
        return True

    @property
    def byte_accounting(self) -> dict[str, Any]:
        """Explicit original / present / missing / corrupted byte accounting.

        The generator never fabricates evidence, so ``reconstructed_bytes`` is
        always ``0`` here. Structural repair belongs to the reconstruction engine
        and must be accounted separately.
        """
        original = self.original_size
        present = self.present_evidence_bytes
        missing = self.missing_byte_count
        corrupted = self.corrupted_byte_count
        return {
            "original_bytes": original,
            "present_evidence_bytes": present,
            "missing_bytes": missing,
            "corrupted_bytes": corrupted,
            "reconstructed_bytes": 0,
            "present_plus_missing_equals_original": present + missing == original,
            "gap_is_physically_absent": self.missing_bytes_absent_from_evidence,
        }

    def to_manifest(self) -> dict[str, Any]:
        """Return a JSON-safe, self-describing ground-truth manifest.

        The byte payloads for original/evidence are saved as separate files by
        ``write_fragment_case``. Ground-truth-only missing bytes are encoded in
        the manifest so a test can verify the exact source range without
        placing those bytes in the evidence artifact.
        """
        ext = ".csv" if self.format == "csv" else ".txt"
        evidence_filename = f"{self.case_id}.evidence{ext}"
        fragment_order = [f.fragment_index for f in self.fragments]
        missing_b64 = (
            base64.b64encode(self.missing_bytes).decode("ascii")
            if self.missing_bytes
            else None
        )
        gap = {
            "gap_start": self.gap_start,
            "gap_end": self.gap_end,
            "gap_length": self.gap_length,
            "missing_sha256": self.missing_sha256,
            "missing_bytes_base64_ground_truth_only": missing_b64,
            "damage_type": self.damage_type,
            "is_physical_missing": self.physical_gap,
            "missing_bytes_absent_from_evidence": self.missing_bytes_absent_from_evidence,
        }
        named_fragments = [
            {
                "offset": fragment.offset,
                "length": fragment.length,
                "sha256": fragment.sha256,
                "source_sha256": fragment.source_sha256,
            }
            for fragment in self.fragments
        ]
        return {
            "case_id": self.case_id,
            "format": self.format,
            "scenario": self.scenario,
            "seed": self.seed,
            "original_filename": self.original_filename,
            "original_file": f"original/{self.original_filename}",
            "original_size": self.original_size,
            "original_sha256": self.original_sha256,
            "evidence_filename": evidence_filename,
            "evidence_size": self.evidence_size,
            "evidence_sha256": self.evidence_sha256,
            "present_evidence": {
                "filename": f"evidence/{evidence_filename}",
                "size": self.evidence_size,
                "sha256": self.evidence_sha256,
                "physical_bytes_only": True,
            },
            "fragments": [
                {
                    "fragment_index": f.fragment_index,
                    "offset": f.offset,
                    "length": f.length,
                    "end_offset": f.end_offset,
                    "sha256": f.sha256,
                    "evidence_offset": f.evidence_offset,
                    "source_sha256": f.source_sha256,
                }
                for f in self.fragments
            ],
            "fragment_a": named_fragments[0] if named_fragments else None,
            "fragment_b": named_fragments[1] if len(named_fragments) > 1 else None,
            "gap": gap,
            "gap_start": self.gap_start,
            "gap_end": self.gap_end,
            "gap_length": self.gap_length,
            "missing_sha256": self.missing_sha256,
            "damage_type": self.damage_type,
            "fragment_order": fragment_order,
            "fragment_count": len(self.fragments),
            "fragments_belong_to_same_artifact": True,
            "physical_gap": self.physical_gap,
            "byte_accounting": self.byte_accounting,
            "reconstruction_ground_truth": {
                "original_filename": self.original_filename,
                "original_size": self.original_size,
                "original_sha256": self.original_sha256,
                "fragment_order": fragment_order,
                "missing_range": (
                    {"start": self.gap_start, "end": self.gap_end}
                    if self.physical_gap
                    else None
                ),
                "missing_bytes_are_ground_truth_only": self.physical_gap,
                "corruption_range": (
                    {"start": self.corruption_start, "end": self.corruption_end}
                    if self.corruption_start is not None
                    else None
                ),
                "byte_accounting": self.byte_accounting,
                "exact_original_available_as": self.original_filename,
            },
        }


def reassemble_from_ground_truth(case: FragmentCase) -> bytes:
    """Rebuild the original from verified present fragments plus ground-truth gap bytes.

    This is a *verification oracle* for the generator's own source mapping, not a
    reconstruction step. It proves::

        original == verified fragment bytes + ground-truth missing bytes

    It reads only ``FragmentCase.original_bytes``; it never consults, synthesises,
    or infers any byte. Corruption scenarios are rejected because their present
    bytes are not the original slice, so no honest reassembly exists.
    """
    if case.scenario == "corrupted":
        raise ValueError(
            "Corrupted cases cannot be reassembled from ground truth: the present "
            "bytes are not the original slice"
        )
    rebuilt = bytearray()
    cursor = 0
    for frag in case.fragments:
        rebuilt.extend(case.original_bytes[cursor : frag.offset])
        rebuilt.extend(
            case.evidence_bytes[
                frag.evidence_offset : frag.evidence_offset + frag.length
            ]
        )
        cursor = frag.end_offset
    rebuilt.extend(case.original_bytes[cursor:])
    return bytes(rebuilt)


def _line_gap_candidates(data: bytes) -> list[tuple[int, int]]:
    """Find deterministic non-empty whole-line ranges that can be omitted."""
    boundaries = [i + 1 for i, byte in enumerate(data) if byte == 0x0A and i + 1 < len(data)]
    candidates = [
        (start, end)
        for i, start in enumerate(boundaries)
        for end in boundaries[i + 1 :]
        if end > start and start > 0 and end < len(data)
    ]
    if candidates:
        return candidates
    if len(data) < 3:
        return []
    # For arbitrary non-line-oriented source bytes, use interior byte offsets.
    start = max(1, len(data) // 3)
    end = min(len(data) - 1, max(start + 1, (2 * len(data)) // 3))
    return [(start, end)] if end > start else []


def _build_fragments(
    original: bytes,
    evidence_parts: list[tuple[int, bytes]],
) -> tuple[bytes, tuple[FragmentDescriptor, ...]]:
    evidence_chunks: list[bytes] = []
    descriptors: list[FragmentDescriptor] = []
    evidence_offset = 0
    for fragment_index, (source_offset, payload) in enumerate(evidence_parts):
        if not payload:
            raise ValueError("Generated fragments must be non-empty")
        source_slice = original[source_offset : source_offset + len(payload)]
        descriptors.append(
            FragmentDescriptor(
                fragment_index=fragment_index,
                offset=source_offset,
                length=len(payload),
                sha256=_sha256(payload),
                evidence_offset=evidence_offset,
                source_sha256=_sha256(source_slice),
            )
        )
        evidence_chunks.append(payload)
        evidence_offset += len(payload)
    return b"".join(evidence_chunks), tuple(descriptors)


def generate_fragment_case(
    original_bytes: bytes,
    *,
    fmt: str,
    seed: int,
    scenario: str = "fragmented",
    original_filename: str | None = None,
    case_id: str | None = None,
) -> FragmentCase:
    """Generate one deterministic TXT/CSV damage case from real source bytes.

    Scenarios are ``clean``, ``fragmented`` (two exact source slices separated
    by an absent range), ``truncated`` (an intact prefix with a missing suffix),
    ``corrupted`` (a single bounded bit-flip region, explicitly marked as
    corruption), and ``unrecoverable`` (a small intact prefix with the remaining
    source physically absent).

    Random choices are seeded with the caller's seed, format, and scenario.
    The evidence stream is always just the concatenation of bytes actually
    present; source offsets are retained separately in each fragment descriptor.
    """
    normalized_format, normalized_scenario = _validate_source(original_bytes, fmt, scenario)
    filename = original_filename or f"ordinary_{normalized_format}_fixture.{normalized_format}"
    if not filename.lower().endswith(f".{normalized_format}"):
        raise ValueError(f"original_filename must have the .{normalized_format} extension")
    case = case_id or f"{normalized_format}_{normalized_scenario}_seed_{seed}"
    rng = random.Random(f"recoverix:{seed}:{normalized_format}:{normalized_scenario}")
    size = len(original_bytes)
    corruption_start: int | None = None
    corruption_end: int | None = None

    if normalized_scenario == "clean":
        evidence_parts = [(0, original_bytes)]
        gap_start = gap_end = size
        missing = b""
        damage_type = "CLEAN_CONTIGUOUS"
    elif normalized_scenario == "fragmented":
        candidates = _line_gap_candidates(original_bytes)
        if not candidates:
            raise ValueError("Source must contain at least 3 bytes to fragment")
        gap_start, gap_end = rng.choice(candidates)
        evidence_parts = [
            (0, original_bytes[:gap_start]),
            (gap_end, original_bytes[gap_end:]),
        ]
        missing = original_bytes[gap_start:gap_end]
        damage_type = "PHYSICAL_GAP"
    elif normalized_scenario == "truncated":
        if size < 2:
            raise ValueError("Source must contain at least 2 bytes to truncate")
        min_cut = max(1, (size * 3) // 4)
        cut = rng.randint(min_cut, size - 1)
        evidence_parts = [(0, original_bytes[:cut])]
        gap_start, gap_end = cut, size
        missing = original_bytes[cut:]
        damage_type = "TRUNCATED_SUFFIX"
    elif normalized_scenario == "corrupted":
        damage_length = max(1, min(size // 12 or 1, size))
        corruption_start = max(0, (size - damage_length) // 2)
        corruption_end = corruption_start + damage_length
        damaged = bytearray(original_bytes)
        for pos in range(corruption_start, corruption_end):
            bit = 1 << rng.randrange(8)
            damaged[pos] ^= bit
        evidence_parts = [(0, bytes(damaged))]
        gap_start = gap_end = size
        missing = b""
        damage_type = "BIT_FLIP_CORRUPTION"
    else:  # unrecoverable
        if size < 2:
            raise ValueError("Source must contain at least 2 bytes for an unrecoverable case")
        surviving_length = max(1, min(size - 1, size // 10))
        evidence_parts = [(0, original_bytes[:surviving_length])]
        gap_start, gap_end = surviving_length, size
        missing = original_bytes[gap_start:gap_end]
        damage_type = "UNRECOVERABLE_PHYSICAL_TRUNCATION"

    evidence_bytes, fragments = _build_fragments(original_bytes, evidence_parts)
    result = FragmentCase(
        case_id=case,
        format=normalized_format,
        scenario=normalized_scenario,
        seed=seed,
        original_filename=filename,
        original_bytes=original_bytes,
        evidence_bytes=evidence_bytes,
        fragments=fragments,
        gap_start=gap_start,
        gap_end=gap_end,
        missing_bytes=missing,
        damage_type=damage_type,
        corruption_start=corruption_start,
        corruption_end=corruption_end,
    )
    _validate_case(result)
    return result


def _validate_case(case: FragmentCase) -> None:
    """Enforce source mapping, output hashes, gap, and manifest invariants."""
    if case.original_size != len(case.original_bytes):
        raise AssertionError("Original-size invariant failed")
    if case.evidence_size != sum(f.length for f in case.fragments):
        raise AssertionError("Evidence size must equal the total present fragment bytes")
    if case.gap_length != len(case.missing_bytes):
        raise AssertionError("Gap length and ground-truth missing byte count differ")
    if case.missing_bytes != case.original_bytes[case.gap_start : case.gap_end]:
        raise AssertionError("Missing range does not match the original source bytes")

    packed = bytearray()
    cursor = 0
    for expected_index, fragment in enumerate(case.fragments):
        if fragment.fragment_index != expected_index:
            raise AssertionError("Fragment order must be deterministic and sequential")
        if fragment.length <= 0 or fragment.offset < 0:
            raise AssertionError("Fragment offset and length must be valid")
        actual = case.evidence_bytes[
            fragment.evidence_offset : fragment.evidence_offset + fragment.length
        ]
        if fragment.evidence_offset != cursor:
            raise AssertionError("Evidence fragment offsets must be packed without padding")
        if _sha256(actual) != fragment.sha256:
            raise AssertionError("Fragment SHA-256 does not match present evidence bytes")
        source = case.original_bytes[fragment.offset : fragment.end_offset]
        if len(source) != fragment.length:
            raise AssertionError("Fragment source range exceeds the original")
        if fragment.source_sha256 != _sha256(source):
            raise AssertionError("Fragment source SHA-256 does not match its original slice")
        if case.scenario != "corrupted" and actual != source:
            raise AssertionError("Uncorrupted fragment bytes differ from their original slice")
        packed.extend(actual)
        cursor += fragment.length
    if bytes(packed) != case.evidence_bytes:
        raise AssertionError("Evidence is not exactly the ordered concatenation of fragments")

    if case.physical_gap and case.scenario != "corrupted":
        reconstructed_from_oracle = (
            case.evidence_bytes[: case.fragments[0].length]
            + case.missing_bytes
            + case.evidence_bytes[case.fragments[0].length :]
        )
        if reconstructed_from_oracle != case.original_bytes:
            raise AssertionError("Present fragments plus ground-truth gap do not equal original")
    if case.scenario == "corrupted":
        if case.corruption_start is None or case.corruption_end is None:
            raise AssertionError("Corrupted case must identify its corruption range")
        if case.evidence_bytes == case.original_bytes:
            raise AssertionError("Corrupted evidence unexpectedly equals the original")

    accounting = case.byte_accounting
    if accounting["reconstructed_bytes"] != 0:
        raise AssertionError("Generator must never report reconstructed bytes")
    if not accounting["present_plus_missing_equals_original"]:
        raise AssertionError(
            "present_evidence_bytes + missing_bytes must equal original_bytes"
        )
    if case.scenario == "corrupted":
        if accounting["missing_bytes"] != 0:
            raise AssertionError("Corruption must not be accounted as missing bytes")
        if accounting["present_evidence_bytes"] != case.original_size:
            raise AssertionError("Corrupted evidence must retain the original byte count")
        if accounting["corrupted_bytes"] <= 0:
            raise AssertionError("Corrupted case must diverge from the original somewhere")
    else:
        if accounting["corrupted_bytes"] != 0:
            raise AssertionError("Non-corrupted case must not report corrupted bytes")
        if not accounting["gap_is_physically_absent"]:
            raise AssertionError("The removed source range is still present in the evidence")
        if case.gap_length and case.present_evidence_bytes + case.gap_length != case.original_size:
            raise AssertionError("Fragments plus physical gap must account for the whole original")
        if reassemble_from_ground_truth(case) != case.original_bytes:
            raise AssertionError("Ground-truth reassembly does not reproduce the original")

    manifest = case.to_manifest()
    if manifest["fragment_count"] != len(case.fragments):
        raise AssertionError("Manifest fragment count is inconsistent")
    if manifest["evidence_size"] != len(case.evidence_bytes):
        raise AssertionError("Manifest evidence size is inconsistent")
    if manifest["original_sha256"] != _sha256(case.original_bytes):
        raise AssertionError("Manifest original digest is inconsistent")
    if manifest["evidence_sha256"] != _sha256(case.evidence_bytes):
        raise AssertionError("Manifest evidence digest is inconsistent")
    if manifest["byte_accounting"] != case.byte_accounting:
        raise AssertionError("Manifest byte accounting is inconsistent")
    if manifest["gap"]["missing_bytes_absent_from_evidence"] is not (
        case.missing_bytes_absent_from_evidence
    ):
        raise AssertionError("Manifest gap-absence flag is inconsistent")


def generate_standard_cases(seed: int = 42) -> list[FragmentCase]:
    """Build all five deterministic scenarios for the ordinary TXT and CSV fixtures."""
    cases: list[FragmentCase] = []
    for fmt, (filename, original) in STANDARD_FIXTURES.items():
        for scenario in SUPPORTED_SCENARIOS:
            cases.append(
                generate_fragment_case(
                    original,
                    fmt=fmt,
                    seed=seed,
                    scenario=scenario,
                    original_filename=filename,
                    case_id=f"{fmt}_{scenario}_seed_{seed}",
                )
            )
    return cases


def write_fragment_case(case: FragmentCase, output_dir: str | Path) -> dict[str, str]:
    """Persist the original, packed evidence, and JSON manifest for one case."""
    root = Path(output_dir)
    original_path = root / "original" / case.original_filename
    evidence_ext = ".csv" if case.format == "csv" else ".txt"
    evidence_path = root / "evidence" / f"{case.case_id}.evidence{evidence_ext}"
    manifest_path = root / "manifests" / f"{case.case_id}.manifest.json"
    original_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    original_path.write_bytes(case.original_bytes)
    evidence_path.write_bytes(case.evidence_bytes)
    manifest_path.write_text(json.dumps(case.to_manifest(), indent=2) + "\n", encoding="utf-8")
    return {
        "original_path": str(original_path.resolve()),
        "evidence_path": str(evidence_path.resolve()),
        "manifest_path": str(manifest_path.resolve()),
    }
