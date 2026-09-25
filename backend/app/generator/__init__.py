"""
Recoverix — Synthetic Evidence Generator

Produces controlled damaged forensic evidence images with deterministic
scenarios (clean, deleted, fragmented, bifragment, corrupted, unrecoverable)
and a machine-readable ground-truth manifest for automated testing.

``fragment_generator`` is the first-class fragment engine: it slices a *real*
source file into exact source-byte fragments separated by a physically absent
range, and records a fully hash-verified ground-truth manifest per case. It
never pads a gap with spaces, zeroes, or noise, and never fabricates evidence.

This is a TEST HARNESS for the future recovery engine.
It does NOT implement scanning, carving, or reconstruction.
"""

from backend.app.generator.disk import EvidenceDisk
from backend.app.generator.corruption import corrupt_region, CorruptionType
from backend.app.generator.ground_truth import GroundTruthManifest
from backend.app.generator.fragment_generator import (
    STANDARD_FIXTURES,
    SUPPORTED_FORMATS,
    SUPPORTED_SCENARIOS,
    FragmentCase,
    FragmentDescriptor,
    generate_fragment_case,
    generate_standard_cases,
    reassemble_from_ground_truth,
    write_fragment_case,
)

__all__ = [
    "EvidenceDisk",
    "corrupt_region",
    "CorruptionType",
    "GroundTruthManifest",
    "STANDARD_FIXTURES",
    "SUPPORTED_FORMATS",
    "SUPPORTED_SCENARIOS",
    "FragmentCase",
    "FragmentDescriptor",
    "generate_fragment_case",
    "generate_standard_cases",
    "reassemble_from_ground_truth",
    "write_fragment_case",
]
