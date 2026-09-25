"""
Recoverix — Synthetic Evidence Generator

Produces controlled damaged forensic evidence images with deterministic
scenarios (clean, deleted, fragmented, bifragment, corrupted, unrecoverable)
and a machine-readable ground-truth manifest for automated testing.

This is a TEST HARNESS for the future recovery engine.
It does NOT implement scanning, carving, or reconstruction.
"""

from backend.app.generator.disk import EvidenceDisk
from backend.app.generator.corruption import corrupt_region, CorruptionType
from backend.app.generator.ground_truth import GroundTruthManifest

__all__ = ["EvidenceDisk", "corrupt_region", "CorruptionType", "GroundTruthManifest"]
