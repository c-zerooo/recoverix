"""
corruption.py — Deterministic corruption operations.

Each corruption type is a simple, reproducible transformation applied
to a region of bytes.  The module does NOT decide *where* to apply
corruption — that is the caller's responsibility.

Corruption metadata returned alongside the mutated bytes is intended
for the ground-truth manifest so tests can verify exactly what changed.
"""

from __future__ import annotations

import enum
import random
from dataclasses import dataclass
from typing import List


class CorruptionType(enum.Enum):
    """Supported corruption operations."""

    ZERO_FILL = "zero_fill"
    """Replace the region with 0x00 bytes."""

    RANDOM_OVERWRITE = "random_overwrite"
    """Overwrite the region with deterministic pseudo-random bytes."""

    BIT_FLIP = "bit_flip"
    """Flip selected bits inside the region."""


@dataclass(frozen=True)
class CorruptionRecord:
    """Machine-readable description of a single corruption operation."""

    corruption_type: str
    offset_within_artifact: int
    length: int
    description: str


def corrupt_region(
    data: bytes,
    offset: int,
    length: int,
    corruption_type: CorruptionType,
    rng: random.Random,
) -> tuple[bytearray, CorruptionRecord]:
    """Apply deterministic corruption to a byte region.

    Args:
        data: The original artifact bytes (not the whole image).
        offset: Start position *within the artifact* to corrupt.
        length: Number of bytes to corrupt.
        corruption_type: Which corruption operation to apply.
        rng: Seeded random.Random instance for reproducibility.

    Returns:
        A (mutated_data, record) tuple.  *mutated_data* is a new
        bytearray with the corruption applied; *record* documents
        what was done.

    Raises:
        ValueError: On out-of-bounds or invalid parameters.
    """
    if offset < 0:
        raise ValueError(f"Corruption offset must be non-negative, got {offset}")
    if length <= 0:
        raise ValueError(f"Corruption length must be positive, got {length}")
    if offset + length > len(data):
        raise ValueError(
            f"Corruption region [{offset}:{offset + length}) "
            f"exceeds artifact size {len(data)}"
        )

    result = bytearray(data)

    if corruption_type == CorruptionType.ZERO_FILL:
        result[offset : offset + length] = b"\x00" * length
        desc = f"Zeroed {length} bytes at artifact offset {offset}"

    elif corruption_type == CorruptionType.RANDOM_OVERWRITE:
        noise = bytes(rng.randint(0, 255) for _ in range(length))
        result[offset : offset + length] = noise
        desc = f"Random-overwritten {length} bytes at artifact offset {offset}"

    elif corruption_type == CorruptionType.BIT_FLIP:
        flipped: List[int] = []
        for i in range(offset, offset + length):
            bit_pos = rng.randint(0, 7)
            result[i] ^= 1 << bit_pos
            flipped.append(bit_pos)
        desc = (
            f"Bit-flipped {length} bytes at artifact offset {offset} "
            f"(bit positions: {flipped})"
        )

    else:
        raise ValueError(f"Unknown corruption type: {corruption_type}")

    record = CorruptionRecord(
        corruption_type=corruption_type.value,
        offset_within_artifact=offset,
        length=length,
        description=desc,
    )
    return result, record
