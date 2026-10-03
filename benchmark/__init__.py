"""Recoverix Benchmark Harness — Measurement & Evaluator Foundation (Milestone 3.7.1).

Provides:
- Machine-readable physical ground truth & observed recovery result schemas.
- Explicit three-space coordinate mapping (Evidence, Original, Recovered).
- Deterministic greedy one-to-one candidate matching.
- Decoupled expectation oracle & deterministic status truth table.
- Mathematical metrics: volume accuracy, interval IoU, byte correctness, status accuracy.
- Dedicated forensic false-recovery auditor.
"""

from __future__ import annotations

from benchmark.models import (
    BenchmarkGroundTruthManifest,
    BenchmarkObservedManifest,
    ObservedArtifactRecoveryResult,
    ObservedCandidateResult,
    ObservedRecoverySegment,
    PhysicalArtifactRecord,
    PhysicalDamageInterval,
    PhysicalPlacement,
    PhysicalRelationshipRecord,
)
from benchmark.matcher import (
    CandidateMatch,
    MatchingResult,
    match_candidates_one_to_one,
)
from benchmark.expectations import (
    DerivedExpectation,
    derive_expected_recovery,
)
from benchmark.metrics import (
    CandidateDetectionMetrics,
    EvaluationMetrics,
    compute_candidate_metrics,
    compute_evaluation_metrics,
    compute_relationship_accuracy,
    compute_interval_iou,
)
from benchmark.evaluator import (
    EvaluationReport,
    audit_false_recovery,
    evaluate_scenario,
)
from benchmark.run_baseline import (
    build_ground_truth_manifest,
    run_baseline_benchmark,
    run_pipeline_and_observe,
)

__all__ = [
    "BenchmarkGroundTruthManifest",
    "BenchmarkObservedManifest",
    "ObservedArtifactRecoveryResult",
    "ObservedCandidateResult",
    "ObservedRecoverySegment",
    "PhysicalArtifactRecord",
    "PhysicalDamageInterval",
    "PhysicalPlacement",
    "PhysicalRelationshipRecord",
    "CandidateMatch",
    "MatchingResult",
    "match_candidates_one_to_one",
    "DerivedExpectation",
    "derive_expected_recovery",
    "CandidateDetectionMetrics",
    "EvaluationMetrics",
    "compute_candidate_metrics",
    "compute_evaluation_metrics",
    "compute_relationship_accuracy",
    "compute_interval_iou",
    "EvaluationReport",
    "audit_false_recovery",
    "evaluate_scenario",
    "build_ground_truth_manifest",
    "run_baseline_benchmark",
    "run_pipeline_and_observe",
]
