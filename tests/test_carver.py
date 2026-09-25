"""
test_carver.py — Tests for the Recoverix contiguous artifact carver.

Covers: contiguous TXT/CSV carving, source offsets, exact bytes, byte count,
carving method, candidate ID and MIME/category preservation, offset zero,
final byte boundary, empty evidence rejection, negative offset rejection,
end-before-start rejection, end beyond evidence rejection, zero-length rejection,
PNG unknown end handling, input immutability, determinism, integration with
seed-42 evidence, and multiple candidates.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure imports work from the project root.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.app.recovery.scanner import Candidate, scan_evidence
from backend.app.recovery.carver import RecoveredArtifact, carve_candidate


# ── Helpers ─────────────────────────────────────────────────────────

def _make_txt_artifact(body_lines: list[str]) -> bytes:
    lines = [
        "[SYNTHETIC_ARTIFACT_START]",
        "filename: test.txt",
        *body_lines,
        "[SYNTHETIC_ARTIFACT_END]",
    ]
    return "\n".join(lines).encode("utf-8")


def _make_csv_artifact(rows: list[list[str]]) -> bytes:
    lines = ["[SYNTHETIC_ARTIFACT_START]"]
    for row in rows:
        lines.append(",".join(row))
    lines.append("[SYNTHETIC_ARTIFACT_END]")
    return "\n".join(lines).encode("utf-8")


# ── 1. Contiguous TXT Carving ──────────────────────────────────────

def test_contiguous_txt_carving():
    artifact = _make_txt_artifact(["content: hello"])
    evidence = b"\x00" * 100 + artifact + b"\x00" * 50

    candidates = scan_evidence(evidence)
    assert len(candidates) == 1
    c = candidates[0]

    recovered = carve_candidate(evidence, c)

    assert isinstance(recovered, RecoveredArtifact)
    assert recovered.format == "txt"
    assert recovered.mime_type == "text/plain"
    assert recovered.category == "text"
    assert recovered.source_offset == 100
    assert recovered.recovered_bytes == artifact
    assert recovered.recovered_byte_count == len(artifact)
    assert recovered.carving_method == "CONTIGUOUS"
    assert recovered.candidate_id == c.candidate_id


# ── 2. Contiguous CSV Carving ──────────────────────────────────────

def test_contiguous_csv_carving():
    artifact = _make_csv_artifact([["col1", "col2"], ["val1", "val2"]])
    evidence = b"\xff" * 42 + artifact

    candidates = scan_evidence(evidence)
    assert len(candidates) == 1
    c = candidates[0]

    recovered = carve_candidate(evidence, c)

    assert recovered.format == "csv"
    assert recovered.mime_type == "text/csv"
    assert recovered.category == "text"
    assert recovered.source_offset == 42
    assert recovered.recovered_bytes == artifact
    assert recovered.recovered_byte_count == len(artifact)
    assert recovered.carving_method == "CONTIGUOUS"


# ── 3. Correct Source Offset ───────────────────────────────────────

def test_correct_source_offset():
    artifact = _make_txt_artifact(["key: value"])
    offset = 512
    evidence = b"\x00" * offset + artifact

    candidates = scan_evidence(evidence)
    recovered = carve_candidate(evidence, candidates[0])

    assert recovered.source_offset == offset


# ── 4. Exact Recovered Bytes & 5. Recovered Byte Count ─────────────

def test_exact_bytes_and_count():
    artifact = _make_txt_artifact(["data: 999"])
    evidence = b"\x11" * 30 + artifact + b"\x22" * 30

    candidates = scan_evidence(evidence)
    recovered = carve_candidate(evidence, candidates[0])

    assert recovered.recovered_bytes == artifact
    assert recovered.recovered_byte_count == len(artifact)


# ── 6. Carving Method ──────────────────────────────────────────────

def test_carving_method():
    artifact = _make_txt_artifact(["test: method"])
    evidence = artifact
    candidates = scan_evidence(evidence)
    recovered = carve_candidate(evidence, candidates[0])

    assert recovered.carving_method == "CONTIGUOUS"


# ── 7. Candidate ID Preservation ───────────────────────────────────

def test_candidate_id_preservation():
    artifact = _make_txt_artifact(["id: test"])
    evidence = artifact
    candidates = scan_evidence(evidence)
    c = candidates[0]

    recovered = carve_candidate(evidence, c)
    assert recovered.candidate_id == c.candidate_id


# ── 8. MIME and Category Preservation ─────────────────────────────

def test_mime_and_category_preservation():
    txt = _make_txt_artifact(["t: 1"])
    csv = _make_csv_artifact([["a", "b"], ["1", "2"]])
    evidence = txt + b"\x00" * 10 + csv

    candidates = scan_evidence(evidence)
    assert len(candidates) == 2

    r_txt = carve_candidate(evidence, candidates[0])
    assert r_txt.mime_type == "text/plain"
    assert r_txt.category == "text"

    r_csv = carve_candidate(evidence, candidates[1])
    assert r_csv.mime_type == "text/csv"
    assert r_csv.category == "text"


# ── 9. Candidate at Offset Zero ────────────────────────────────────

def test_candidate_at_offset_zero():
    artifact = _make_txt_artifact(["start: zero"])
    evidence = artifact + b"\x00" * 100

    candidates = scan_evidence(evidence)
    recovered = carve_candidate(evidence, candidates[0])

    assert recovered.source_offset == 0
    assert recovered.recovered_bytes == artifact


# ── 10. Candidate Ending at Final Byte ─────────────────────────────

def test_candidate_ending_at_final_byte():
    padding = b"\x00" * 200
    artifact = _make_txt_artifact(["at: end"])
    evidence = padding + artifact

    candidates = scan_evidence(evidence)
    recovered = carve_candidate(evidence, candidates[0])

    assert recovered.source_offset == 200
    assert recovered.source_offset + recovered.recovered_byte_count == len(evidence)


# ── 11. Empty Evidence Rejection ───────────────────────────────────

def test_empty_evidence_rejection():
    c = Candidate(
        candidate_id="cand-0",
        format="txt",
        mime_type="text/plain",
        category="text",
        offset=0,
        detected_header_length=25,
        estimated_end_offset=10,
        detection_method="synthetic_boundary",
    )
    with pytest.raises(ValueError, match="empty evidence"):
        carve_candidate(b"", c)


# ── 12. Negative Offset Rejection ──────────────────────────────────
def test_negative_offset_rejection():
    c = Candidate(
        candidate_id="cand-0",
        format="txt",
        mime_type="text/plain",
        category="text",
        offset=-1,
        detected_header_length=25,
        estimated_end_offset=10,
        detection_method="synthetic_boundary",
    )
    with pytest.raises(ValueError, match="negative"):
        carve_candidate(b"some evidence data here", c)


# ── 13. End-Before-Start Rejection ─────────────────────────────────

def test_end_before_start_rejection():
    c = Candidate(
        candidate_id="cand-0",
        format="txt",
        mime_type="text/plain",
        category="text",
        offset=50,
        detected_header_length=25,
        estimated_end_offset=20,
        detection_method="synthetic_boundary",
    )
    with pytest.raises(ValueError, match="cannot be less than offset"):
        carve_candidate(b"\x00" * 100, c)


# ── 14. End Beyond Evidence Rejection ──────────────────────────────

def test_end_beyond_evidence_rejection():
    artifact = _make_txt_artifact(["short"])
    evidence = artifact
    c = Candidate(
        candidate_id="cand-0",
        format="txt",
        mime_type="text/plain",
        category="text",
        offset=0,
        detected_header_length=25,
        estimated_end_offset=len(evidence) + 50,
        detection_method="synthetic_boundary",
    )
    with pytest.raises(ValueError, match="exceeds evidence size"):
        carve_candidate(evidence, c)


# ── 15. Zero-Length Candidate Rejection ────────────────────────────

def test_zero_length_candidate_rejection():
    c = Candidate(
        candidate_id="cand-0",
        format="txt",
        mime_type="text/plain",
        category="text",
        offset=10,
        detected_header_length=25,
        estimated_end_offset=10,
        detection_method="synthetic_boundary",
    )
    with pytest.raises(ValueError, match="zero length"):
        carve_candidate(b"\x00" * 100, c)


# ── 16. PNG Candidate with Unknown End Handled Safely ──────────────

def test_png_candidate_unknown_end_handled_safely():
    from backend.app.recovery.signatures import PNG_SIGNATURE
    evidence = PNG_SIGNATURE + b"\x00" * 100
    candidates = scan_evidence(evidence)

    png_candidates = [c for c in candidates if c.format == "png"]
    assert len(png_candidates) == 1
    c = png_candidates[0]
    assert c.estimated_end_offset is None

    with pytest.raises(ValueError, match="estimated_end_offset is None"):
        carve_candidate(evidence, c)


# ── 17. Input Evidence Remains Unchanged ───────────────────────────

def test_input_evidence_unchanged():
    artifact = _make_txt_artifact(["immutable: yes"])
    evidence = bytearray(b"\x00" * 50 + artifact + b"\x00" * 50)
    original = bytes(evidence)

    candidates = scan_evidence(bytes(evidence))
    carve_candidate(bytes(evidence), candidates[0])

    assert bytes(evidence) == original


# ── 18. Deterministic Repeated Carving ─────────────────────────────

def test_deterministic_carving():
    artifact = _make_txt_artifact(["repeat: check"])
    evidence = b"\xaa" * 20 + artifact + b"\xbb" * 20

    candidates = scan_evidence(evidence)
    c = candidates[0]

    r1 = carve_candidate(evidence, c)
    r2 = carve_candidate(evidence, c)

    assert r1 == r2
    assert r1.recovered_bytes == r2.recovered_bytes


# ── 19. Integration with Generated Seed-42 Evidence ────────────────

def test_carve_generated_evidence(tmp_path):
    from backend.generate_case import generate_evidence

    generate_evidence(42, tmp_path)
    img = (tmp_path / "damaged.img").read_bytes()

    candidates = scan_evidence(img)
    assert len(candidates) >= 1

    # Carve the first valid candidate with an estimated end offset.
    carveable = [c for c in candidates if c.estimated_end_offset is not None]
    assert len(carveable) >= 1

    c = carveable[0]
    recovered = carve_candidate(img, c)

    assert recovered.recovered_byte_count > 0
    assert recovered.source_offset == c.offset
    assert recovered.carving_method == "CONTIGUOUS"


# ── 20. Multiple Contiguous Candidates ─────────────────────────────

def test_multiple_contiguous_candidates():
    a1 = _make_txt_artifact(["item: 1"])
    a2 = _make_csv_artifact([["col"], ["val"]])
    gap = b"\x00" * 32
    evidence = a1 + gap + a2

    candidates = scan_evidence(evidence)
    assert len(candidates) == 2

    r1 = carve_candidate(evidence, candidates[0])
    r2 = carve_candidate(evidence, candidates[1])

    assert r1.recovered_bytes == a1
    assert r2.recovered_bytes == a2
    assert r1.source_offset < r2.source_offset


# ── Additional Safety & Type Checks ─────────────────────────────────

def test_invalid_candidate_type():
    with pytest.raises(TypeError, match="Expected Candidate object"):
        carve_candidate(b"data", "not-a-candidate")  # type: ignore[arg-type]
