from __future__ import annotations

import base64
import hashlib
import json

import pytest

from backend.app.generator.fragment_generator import (
    STANDARD_FIXTURES,
    SUPPORTED_FORMATS,
    SUPPORTED_SCENARIOS,
    generate_fragment_case,
    generate_standard_cases,
    reassemble_from_ground_truth,
    write_fragment_case,
)


def _fixture(fmt: str) -> tuple[str, bytes]:
    return STANDARD_FIXTURES[fmt]


@pytest.mark.parametrize("fmt", ["txt", "csv"])
def test_clean_case_is_an_exact_contiguous_source(fmt: str) -> None:
    filename, original = _fixture(fmt)
    case = generate_fragment_case(
        original, fmt=fmt, seed=42, scenario="clean", original_filename=filename
    )

    assert case.evidence_bytes == original
    assert case.evidence_size == case.original_size
    assert case.gap_length == 0
    assert case.missing_bytes == b""
    assert case.physical_gap is False
    assert len(case.fragments) == 1
    fragment = case.fragments[0]
    assert fragment.offset == 0
    assert fragment.length == len(original)
    assert fragment.sha256 == hashlib.sha256(original).hexdigest()
    assert fragment.source_sha256 == fragment.sha256


@pytest.mark.parametrize("fmt", ["txt", "csv"])
def test_fragmented_case_uses_exact_source_slices_and_physically_omits_gap(fmt: str) -> None:
    filename, original = _fixture(fmt)
    case = generate_fragment_case(
        original, fmt=fmt, seed=42, scenario="fragmented", original_filename=filename
    )
    fragment_a, fragment_b = case.fragments

    assert case.physical_gap is True
    assert case.gap_length == len(case.missing_bytes) > 0
    assert (case.gap_start, case.gap_end) == (fragment_a.end_offset, fragment_b.offset)
    assert fragment_a.offset == 0
    assert fragment_a.length == case.gap_start
    assert fragment_b.end_offset == len(original)
    assert case.missing_bytes == original[case.gap_start : case.gap_end]
    assert case.evidence_bytes == original[: case.gap_start] + original[case.gap_end :]
    assert len(case.evidence_bytes) == len(original) - case.gap_length

    # The gap is a real omitted source range, not a zero/space/noise placeholder.
    fragment_a_bytes = case.evidence_bytes[: fragment_a.length]
    fragment_b_bytes = case.evidence_bytes[fragment_a.length :]
    assert case.evidence_bytes == fragment_a_bytes + fragment_b_bytes
    assert case.evidence_bytes.find(case.missing_bytes) == -1
    assert fragment_a_bytes == original[fragment_a.offset : fragment_a.end_offset]
    assert fragment_b_bytes == original[fragment_b.offset : fragment_b.end_offset]
    assert hashlib.sha256(fragment_a_bytes).hexdigest() == fragment_a.sha256
    assert hashlib.sha256(fragment_b_bytes).hexdigest() == fragment_b.sha256
    assert hashlib.sha256(case.missing_bytes).hexdigest() == case.missing_sha256
    assert fragment_a.evidence_offset == 0
    assert fragment_b.evidence_offset == fragment_a.length
    assert fragment_a.fragment_index == 0
    assert fragment_b.fragment_index == 1
    assert fragment_a_bytes + case.missing_bytes + fragment_b_bytes == original


@pytest.mark.parametrize("fmt", ["txt", "csv"])
def test_truncated_case_has_intact_prefix_and_real_missing_suffix(fmt: str) -> None:
    filename, original = _fixture(fmt)
    case = generate_fragment_case(
        original, fmt=fmt, seed=42, scenario="truncated", original_filename=filename
    )

    assert len(case.fragments) == 1
    fragment = case.fragments[0]
    assert case.evidence_bytes == original[: fragment.length]
    assert fragment.offset == 0
    assert case.gap_start == fragment.length
    assert case.gap_end == len(original)
    assert case.missing_bytes == original[fragment.length :]
    assert case.evidence_size + case.gap_length == case.original_size
    assert case.missing_bytes not in case.evidence_bytes
    assert hashlib.sha256(case.evidence_bytes).hexdigest() == fragment.sha256


@pytest.mark.parametrize("fmt", ["txt", "csv"])
def test_corrupted_case_is_distinguished_from_missing_bytes(fmt: str) -> None:
    filename, original = _fixture(fmt)
    case = generate_fragment_case(
        original, fmt=fmt, seed=42, scenario="corrupted", original_filename=filename
    )

    assert case.gap_length == 0
    assert case.missing_bytes == b""
    assert case.physical_gap is False
    assert case.evidence_size == case.original_size
    assert case.evidence_bytes != original
    assert case.corruption_start is not None
    assert case.corruption_end is not None
    assert 0 <= case.corruption_start < case.corruption_end <= len(original)
    assert case.evidence_bytes[: case.corruption_start] == original[: case.corruption_start]
    assert case.evidence_bytes[case.corruption_end :] == original[case.corruption_end :]
    assert case.damage_type == "BIT_FLIP_CORRUPTION"
    assert case.fragments[0].sha256 == hashlib.sha256(case.evidence_bytes).hexdigest()
    assert case.fragments[0].source_sha256 == hashlib.sha256(original).hexdigest()


@pytest.mark.parametrize("fmt", ["txt", "csv"])
def test_unrecoverable_case_retains_only_a_real_prefix(fmt: str) -> None:
    filename, original = _fixture(fmt)
    case = generate_fragment_case(
        original, fmt=fmt, seed=42, scenario="unrecoverable", original_filename=filename
    )

    assert len(case.fragments) == 1
    fragment = case.fragments[0]
    assert case.evidence_bytes == original[: fragment.length]
    assert case.gap_start == fragment.length
    assert case.gap_end == len(original)
    assert case.gap_length == len(original) - len(case.evidence_bytes) > 0
    assert case.missing_bytes == original[fragment.length :]
    assert case.missing_bytes not in case.evidence_bytes
    assert case.damage_type == "UNRECOVERABLE_PHYSICAL_TRUNCATION"


def test_seed_reproduces_original_fixture_evidence_and_manifest() -> None:
    first = generate_standard_cases(seed=9182)
    second = generate_standard_cases(seed=9182)

    assert len(first) == len(second) == 2 * len(SUPPORTED_SCENARIOS)
    for a, b in zip(first, second):
        assert a.case_id == b.case_id
        assert a.original_bytes == b.original_bytes
        assert a.evidence_bytes == b.evidence_bytes
        assert a.to_manifest() == b.to_manifest()


def test_different_seed_changes_fragment_or_damage_choice() -> None:
    filename, original = _fixture("txt")
    a = generate_fragment_case(
        original, fmt="txt", seed=2, scenario="fragmented", original_filename=filename
    )
    b = generate_fragment_case(
        original, fmt="txt", seed=99, scenario="fragmented", original_filename=filename
    )
    assert (a.gap_start, a.gap_end) != (b.gap_start, b.gap_end)


@pytest.mark.parametrize("fmt", ["txt", "csv"])
def test_manifest_has_required_hashes_ranges_and_ground_truth(fmt: str) -> None:
    filename, original = _fixture(fmt)
    case = generate_fragment_case(
        original, fmt=fmt, seed=7, scenario="fragmented", original_filename=filename
    )
    manifest = case.to_manifest()
    gap = manifest["gap"]

    assert manifest["case_id"] == case.case_id
    assert manifest["format"] == fmt
    assert manifest["seed"] == 7
    assert manifest["original_filename"] == filename
    assert manifest["original_size"] == len(original)
    assert manifest["original_sha256"] == hashlib.sha256(original).hexdigest()
    assert manifest["evidence_size"] == len(case.evidence_bytes)
    assert manifest["evidence_sha256"] == hashlib.sha256(case.evidence_bytes).hexdigest()
    assert manifest["fragment_order"] == [0, 1]
    assert manifest["fragment_count"] == 2
    assert manifest["fragments_belong_to_same_artifact"] is True
    assert manifest["physical_gap"] is True
    assert gap["gap_start"] == case.gap_start
    assert gap["gap_end"] == case.gap_end
    assert gap["gap_length"] == case.gap_length
    assert gap["damage_type"] == "PHYSICAL_GAP"
    assert gap["is_physical_missing"] is True
    assert gap["missing_sha256"] == hashlib.sha256(case.missing_bytes).hexdigest()
    assert base64.b64decode(gap["missing_bytes_base64_ground_truth_only"]) == case.missing_bytes
    assert len(manifest["fragments"]) == 2
    for described, fragment in zip(manifest["fragments"], case.fragments):
        assert described["offset"] == fragment.offset
        assert described["length"] == fragment.length
        assert described["sha256"] == fragment.sha256
        assert described["source_sha256"] == hashlib.sha256(
            original[fragment.offset : fragment.end_offset]
        ).hexdigest()
    ground_truth = manifest["reconstruction_ground_truth"]
    assert ground_truth["missing_range"] == {"start": case.gap_start, "end": case.gap_end}
    assert ground_truth["missing_bytes_are_ground_truth_only"] is True
    assert ground_truth["original_sha256"] == manifest["original_sha256"]


def test_all_standard_cases_cover_both_formats_and_all_damage_scenarios() -> None:
    cases = generate_standard_cases(seed=314)
    assert {(case.format, case.scenario) for case in cases} == {
        (fmt, scenario)
        for fmt in ("txt", "csv")
        for scenario in SUPPORTED_SCENARIOS
    }
    assert all(b"[SYNTHETIC_ARTIFACT_" not in case.original_bytes for case in cases)


def test_writer_persists_original_present_evidence_and_manifest(tmp_path) -> None:
    filename, original = _fixture("csv")
    case = generate_fragment_case(
        original, fmt="csv", seed=11, scenario="fragmented", original_filename=filename
    )

    paths = write_fragment_case(case, tmp_path)
    original_path = tmp_path / "original" / filename
    evidence_path = tmp_path / "evidence" / f"{case.case_id}.evidence.csv"
    manifest_path = tmp_path / "manifests" / f"{case.case_id}.manifest.json"

    assert paths == {
        "original_path": str(original_path.resolve()),
        "evidence_path": str(evidence_path.resolve()),
        "manifest_path": str(manifest_path.resolve()),
    }
    assert original_path.read_bytes() == case.original_bytes
    assert evidence_path.read_bytes() == case.evidence_bytes
    persisted_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert persisted_manifest == case.to_manifest()
    assert evidence_path.stat().st_size == case.original_size - case.gap_length


def test_rejects_unknown_format_and_scenario() -> None:
    with pytest.raises(ValueError, match="Unsupported format"):
        generate_fragment_case(b"data", fmt="json", seed=1)
    with pytest.raises(ValueError, match="Unsupported scenario"):
        generate_fragment_case(b"data", fmt="txt", seed=1, scenario="unknown")


ALL_CASES = [
    (fmt, scenario)
    for fmt in SUPPORTED_FORMATS
    for scenario in SUPPORTED_SCENARIOS
]


def _all_cases() -> list:
    return [
        generate_fragment_case(
            _fixture(fmt)[1],
            fmt=fmt,
            seed=2026,
            scenario=scenario,
            original_filename=_fixture(fmt)[0],
            case_id=f"{fmt}_{scenario}",
        )
        for fmt, scenario in ALL_CASES
    ]


@pytest.mark.parametrize("fmt", SUPPORTED_FORMATS)
@pytest.mark.parametrize("scenario", SUPPORTED_SCENARIOS)
def test_every_damage_scenario_is_produced_for_both_formats(fmt: str, scenario: str) -> None:
    filename, original = _fixture(fmt)
    case = generate_fragment_case(
        original, fmt=fmt, seed=2026, scenario=scenario, original_filename=filename
    )
    assert case.format == fmt
    assert case.scenario == scenario
    assert case.original_bytes == original
    assert case.evidence_size > 0
    assert case.fragments


@pytest.mark.parametrize("fmt,scenario", ALL_CASES)
def test_ground_truth_invariant_fragments_are_exact_original_slices(fmt: str, scenario: str) -> None:
    """Invariants 1-4: fragment bytes, SHA-256, offsets and lengths are exact."""
    filename, original = _fixture(fmt)
    case = generate_fragment_case(
        original, fmt=fmt, seed=2026, scenario=scenario, original_filename=filename
    )

    for expected_index, fragment in enumerate(case.fragments):
        assert fragment.fragment_index == expected_index
        present = case.evidence_bytes[
            fragment.evidence_offset : fragment.evidence_offset + fragment.length
        ]
        assert fragment.length == len(present)
        assert hashlib.sha256(present).hexdigest() == fragment.sha256
        assert fragment.source_sha256 == hashlib.sha256(
            original[fragment.offset : fragment.end_offset]
        ).hexdigest()
        assert 0 <= fragment.offset < fragment.end_offset <= len(original)
        if scenario != "corrupted":
            assert present == original[fragment.offset : fragment.end_offset]
        else:
            assert fragment.sha256 != fragment.source_sha256


@pytest.mark.parametrize("fmt,scenario", ALL_CASES)
def test_ground_truth_invariant_gap_range_and_missing_bytes(fmt: str, scenario: str) -> None:
    """Invariants 5-7: gap range is correct and the missing bytes are truly gone."""
    filename, original = _fixture(fmt)
    case = generate_fragment_case(
        original, fmt=fmt, seed=2026, scenario=scenario, original_filename=filename
    )

    assert case.gap_start <= case.gap_end <= len(original)
    assert case.gap_length == case.gap_end - case.gap_start
    assert case.gap_length == case.missing_byte_count
    assert case.missing_bytes == original[case.gap_start : case.gap_end]
    assert case.missing_bytes_absent_from_evidence is True

    for fragment in case.fragments:
        assert fragment.end_offset <= case.gap_start or fragment.offset >= case.gap_end
    if case.gap_length:
        assert case.missing_bytes not in case.evidence_bytes


@pytest.mark.parametrize("fmt,scenario", ALL_CASES)
def test_ground_truth_invariant_ordering_is_deterministic(fmt: str, scenario: str) -> None:
    """Invariant 8: fragment ordering is stable and evidence is a packed concatenation."""
    filename, original = _fixture(fmt)
    case = generate_fragment_case(
        original, fmt=fmt, seed=2026, scenario=scenario, original_filename=filename
    )

    assert [f.fragment_index for f in case.fragments] == list(range(len(case.fragments)))
    offsets = [f.offset for f in case.fragments]
    assert offsets == sorted(offsets)
    assert [f.evidence_offset for f in case.fragments] == sorted(
        f.evidence_offset for f in case.fragments
    )
    assert case.evidence_bytes == b"".join(
        case.evidence_bytes[f.evidence_offset : f.evidence_offset + f.length]
        for f in case.fragments
    )


@pytest.mark.parametrize("fmt,scenario", ALL_CASES)
def test_ground_truth_invariant_manifest_is_internally_consistent(fmt: str, scenario: str) -> None:
    """Invariant 9: the manifest agrees with the bytes it describes."""
    filename, original = _fixture(fmt)
    case = generate_fragment_case(
        original, fmt=fmt, seed=2026, scenario=scenario, original_filename=filename
    )
    manifest = case.to_manifest()

    assert manifest["case_id"] == case.case_id
    assert manifest["format"] == fmt
    assert manifest["scenario"] == scenario
    assert manifest["original_size"] == len(original)
    assert manifest["original_sha256"] == hashlib.sha256(original).hexdigest()
    assert manifest["evidence_size"] == len(case.evidence_bytes)
    assert manifest["evidence_sha256"] == hashlib.sha256(case.evidence_bytes).hexdigest()
    assert manifest["fragment_count"] == len(case.fragments)
    assert manifest["fragment_order"] == [f.fragment_index for f in case.fragments]
    assert manifest["fragments_belong_to_same_artifact"] is True
    assert manifest["physical_gap"] is (case.gap_length > 0)
    assert manifest["gap_start"] == case.gap_start
    assert manifest["gap_end"] == case.gap_end
    assert manifest["gap_length"] == case.gap_length
    assert manifest["damage_type"] == case.damage_type
    assert manifest["gap"]["missing_sha256"] == case.missing_sha256
    assert manifest["gap"]["missing_bytes_absent_from_evidence"] is True
    assert manifest["reconstruction_ground_truth"]["original_sha256"] == manifest["original_sha256"]
    assert json.loads(json.dumps(manifest)) == manifest


@pytest.mark.parametrize("fmt,scenario", ALL_CASES)
def test_byte_accounting_separates_present_missing_and_corrupted(fmt: str, scenario: str) -> None:
    filename, original = _fixture(fmt)
    case = generate_fragment_case(
        original, fmt=fmt, seed=2026, scenario=scenario, original_filename=filename
    )
    accounting = case.byte_accounting

    assert accounting["original_bytes"] == len(original)
    assert accounting["present_evidence_bytes"] == case.evidence_size
    assert accounting["missing_bytes"] == case.gap_length
    assert accounting["reconstructed_bytes"] == 0
    assert accounting["present_plus_missing_equals_original"] is True
    assert accounting["gap_is_physically_absent"] is True

    if scenario == "corrupted":
        # Corruption is present-but-divergent, never accounted as missing bytes.
        assert accounting["missing_bytes"] == 0
        assert accounting["corrupted_bytes"] > 0
        assert accounting["present_evidence_bytes"] == len(original)
    else:
        assert accounting["corrupted_bytes"] == 0
        assert case.present_evidence_bytes + case.gap_length == len(original)


@pytest.mark.parametrize("fmt,scenario", ALL_CASES)
def test_original_equals_verified_fragments_plus_ground_truth_missing(fmt: str, scenario: str) -> None:
    """original == verified fragment bytes + ground-truth missing bytes."""
    filename, original = _fixture(fmt)
    case = generate_fragment_case(
        original, fmt=fmt, seed=2026, scenario=scenario, original_filename=filename
    )

    if scenario == "corrupted":
        with pytest.raises(ValueError, match="Corrupted cases cannot be reassembled"):
            reassemble_from_ground_truth(case)
        return

    rebuilt = reassemble_from_ground_truth(case)
    assert rebuilt == original
    assert hashlib.sha256(rebuilt).hexdigest() == hashlib.sha256(original).hexdigest()

    present_total = sum(f.length for f in case.fragments)
    assert present_total + case.gap_length == len(original)


def test_all_standard_cases_satisfy_every_ground_truth_invariant() -> None:
    for case in generate_standard_cases(seed=555):
        assert case.original_bytes == STANDARD_FIXTURES[case.format][1]
        if case.scenario != "corrupted":
            assert reassemble_from_ground_truth(case) == case.original_bytes
        else:
            with pytest.raises(ValueError, match="Corrupted cases cannot be reassembled"):
                reassemble_from_ground_truth(case)
        assert case.missing_bytes_absent_from_evidence is True
        assert case.byte_accounting["present_plus_missing_equals_original"] is True
        assert case.byte_accounting["reconstructed_bytes"] == 0
        manifest = case.to_manifest()
        assert manifest["byte_accounting"] == case.byte_accounting


def test_generator_never_pads_the_gap_with_zeroes_spaces_or_noise() -> None:
    """A physical gap is absence, not a placeholder payload."""
    for fmt in SUPPORTED_FORMATS:
        filename, original = _fixture(fmt)
        case = generate_fragment_case(
            original, fmt=fmt, seed=808, scenario="fragmented", original_filename=filename
        )
        assert case.gap_length > 0
        assert len(case.evidence_bytes) == len(original) - case.gap_length
        # The evidence is strictly shorter than the original: nothing was inserted.
        assert case.evidence_size < case.original_size
        assert case.evidence_bytes.count(b"\x00" * case.gap_length) == 0
        joined = b"".join(
            case.evidence_bytes[f.evidence_offset : f.evidence_offset + f.length]
            for f in case.fragments
        )
        assert joined == case.evidence_bytes
        assert case.missing_bytes not in joined


def test_generation_is_reproducible_across_seeds_and_calls() -> None:
    first = generate_standard_cases(seed=4242)
    second = generate_standard_cases(seed=4242)
    for a, b in zip(first, second):
        assert a.evidence_bytes == b.evidence_bytes
        assert a.missing_bytes == b.missing_bytes
        assert (a.gap_start, a.gap_end) == (b.gap_start, b.gap_end)
        assert [f.sha256 for f in a.fragments] == [f.sha256 for f in b.fragments]


def test_fixtures_are_real_ordinary_content_not_synthetic_markers() -> None:
    for fmt in SUPPORTED_FORMATS:
        filename, original = STANDARD_FIXTURES[fmt]
        assert filename.endswith(f".{fmt}")
        assert b"SYNTHETIC" not in original
        assert b"ARTIFACT_START" not in original
        text = original.decode("utf-8")
        assert text.endswith("\n")
        if fmt == "csv":
            header, *rows = text.strip().splitlines()
            width = len(header.split(","))
            assert len(rows) >= 3
            assert all(len(r.split(",")) == width for r in rows)
        else:
            assert len(text.strip().splitlines()) >= 4


def test_write_fragment_case_never_writes_the_missing_bytes_into_the_evidence(tmp_path) -> None:
    filename, original = _fixture("txt")
    case = generate_fragment_case(
        original, fmt="txt", seed=64, scenario="fragmented", original_filename=filename
    )
    paths = write_fragment_case(case, tmp_path)

    evidence_on_disk = open(paths["evidence_path"], "rb").read()
    original_on_disk = open(paths["original_path"], "rb").read()

    assert original_on_disk == original
    assert evidence_on_disk == case.evidence_bytes
    assert case.missing_bytes not in evidence_on_disk
    assert len(evidence_on_disk) == len(original) - case.gap_length
