"""benchmark/matcher.py — Deterministic Greedy One-to-One Candidate Matcher.

Implements the approved deterministic greedy one-to-one matching algorithm
between observed recovery candidates and physical ground-truth artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple
from benchmark.models import ObservedCandidateResult, PhysicalArtifactRecord


def compute_span_iou(
    start_a: int,
    end_a: int,
    start_b: int,
    end_b: int,
) -> float:
    """Compute Intersection over Union (IoU) of two half-open intervals [s, e)."""
    if end_a <= start_a or end_b <= start_b:
        return 0.0
    inter_start = max(start_a, start_b)
    inter_end = min(end_a, end_b)
    inter_len = max(0, inter_end - inter_start)
    if inter_len == 0:
        return 0.0
    len_a = end_a - start_a
    len_b = end_b - start_b
    union_len = len_a + len_b - inter_len
    if union_len <= 0:
        return 0.0
    return inter_len / union_len


@dataclass(frozen=True)
class CandidateMatch:
    """One deterministic true-positive match between candidate and ground-truth artifact."""

    candidate: ObservedCandidateResult
    artifact: PhysicalArtifactRecord
    iou: float


@dataclass(frozen=True)
class MatchingResult:
    """Complete results of deterministic one-to-one candidate matching."""

    matched_pairs: List[CandidateMatch] = field(default_factory=list)
    unmatched_candidates: List[ObservedCandidateResult] = field(default_factory=list)
    unmatched_artifacts: List[PhysicalArtifactRecord] = field(default_factory=list)
    duplicate_candidates: List[ObservedCandidateResult] = field(default_factory=list)

    @property
    def true_positives(self) -> int:
        return len(self.matched_pairs)

    @property
    def false_positives(self) -> int:
        return len(self.unmatched_candidates)

    @property
    def false_negatives(self) -> int:
        return len(self.unmatched_artifacts)

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom > 0 else 0.0


def _get_artifact_evidence_span(artifact: PhysicalArtifactRecord) -> Tuple[int, int]:
    """Return the total physical evidence span [start, end) spanned by artifact placements."""
    start = artifact.header_evidence_offset
    end = max(p.evidence_offset + p.evidence_length for p in artifact.placements)
    return (start, end)


def match_candidates_one_to_one(
    gt_artifacts: Sequence[PhysicalArtifactRecord],
    observed_candidates: Sequence[ObservedCandidateResult],
    evidence_buffer_id: Optional[str] = None,
) -> MatchingResult:
    """Match candidates to ground-truth artifacts deterministically using greedy selection.

    Admissibility Rules:
      1. Matching evidence_buffer_id
      2. Matching format (case-insensitive)
      3. Exact start offset match: candidate.offset == artifact.header_evidence_offset
      4. If candidate is bounded: IoU(span(candidate), span(artifact)) > 0

    Ranking Priority:
      1. IoU descending
      2. Span difference |len(c) - len(a)| ascending
      3. artifact_id ascending
      4. candidate_id ascending

    Returns:
      MatchingResult with true positives, false positives, false negatives, and duplicates.
    """
    # 1. Build admissible pairs
    admissible: List[Tuple[float, int, str, str, ObservedCandidateResult, PhysicalArtifactRecord]] = []

    for art in gt_artifacts:
        art_start, art_end = _get_artifact_evidence_span(art)
        art_len = art_end - art_start

        for cand in observed_candidates:
            # Check buffer scope
            if evidence_buffer_id is not None and cand.evidence_buffer_id != evidence_buffer_id:
                continue

            # Check format
            if cand.format.lower() != art.format.lower():
                continue

            # Exact signature header start match
            if cand.offset != art.header_evidence_offset:
                continue

            # Check span IoU for bounded candidates
            if not cand.is_unbounded and cand.estimated_end_offset is not None:
                cand_len = cand.estimated_end_offset - cand.offset
                iou = compute_span_iou(cand.offset, cand.estimated_end_offset, art_start, art_end)
                if iou <= 0.0:
                    continue
                span_diff = abs(cand_len - art_len)
            else:
                # Unbounded candidate matches start; IoU nominally 1.0 for ranking priority
                iou = 1.0
                span_diff = 0

            # Rank tuple: (-iou, span_diff, art.artifact_id, cand.candidate_id, cand, art)
            admissible.append((
                -iou,
                span_diff,
                art.artifact_id,
                cand.candidate_id,
                cand,
                art,
            ))

    # 2. Sort admissible pairs deterministically
    admissible.sort(key=lambda item: (item[0], item[1], item[2], item[3]))

    # 3. Greedy selection
    matched_candidates: set[str] = set()
    matched_artifacts: set[str] = set()
    matches: List[CandidateMatch] = []
    duplicates: List[ObservedCandidateResult] = []

    for neg_iou, _, _, _, cand, art in admissible:
        iou = -neg_iou
        if cand.candidate_id not in matched_candidates and art.artifact_id not in matched_artifacts:
            matched_candidates.add(cand.candidate_id)
            matched_artifacts.add(art.artifact_id)
            matches.append(CandidateMatch(candidate=cand, artifact=art, iou=iou))
        elif art.artifact_id in matched_artifacts and cand.candidate_id not in matched_candidates:
            # Candidate attempted to claim an already-matched artifact -> duplicate
            matched_candidates.add(cand.candidate_id)
            duplicates.append(cand)

    # 4. Form FP and FN sets
    all_matched_cand_ids = {m.candidate.candidate_id for m in matches}
    unmatched_cands: List[ObservedCandidateResult] = [
        c for c in observed_candidates if c.candidate_id not in all_matched_cand_ids
    ]
    unmatched_arts: List[PhysicalArtifactRecord] = [
        a for a in gt_artifacts if a.artifact_id not in matched_artifacts
    ]

    return MatchingResult(
        matched_pairs=matches,
        unmatched_candidates=unmatched_cands,
        unmatched_artifacts=unmatched_arts,
        duplicate_candidates=duplicates,
    )
