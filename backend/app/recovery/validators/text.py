"""
text.py — Deterministic TXT artifact structural validator.

Validates recovered TXT artifact bytes against synthetic harness boundaries (if present)
or plain UTF-8 encoding requirements.
"""

from __future__ import annotations

from typing import Union, Any

from backend.app.models.validation import ValidationResult
from backend.app.recovery.carver import RecoveredArtifact
from backend.app.recovery.signatures import (
    SYNTHETIC_START_MARKER,
    SYNTHETIC_END_MARKER,
)


def validate_txt(data: bytes | RecoveredArtifact) -> ValidationResult:
    """Validate the structural integrity of a recovered TXT artifact.

    Accepts raw bytes or a RecoveredArtifact object.

    Checks performed:
      1. input_type: input is bytes (or RecoveredArtifact yielding bytes)
      2. non_empty: input is non-empty
      3. synthetic markers check (if present: start_marker_exists, end_marker_exists, marker_ordering)
      4. utf8_decoding: payload can be safely decoded as UTF-8

    Args:
        data: Raw evidence bytes or RecoveredArtifact.

    Returns:
        ValidationResult with validation outcome, checks, errors, and details.
    """
    checks: list[str] = [
        "input_type",
        "non_empty",
        "utf8_decoding",
    ]
    errors: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {}

    # Extract raw bytes and format
    raw_bytes: bytes
    fmt: str = "txt"
    if isinstance(data, RecoveredArtifact):
        raw_bytes = data.recovered_bytes
        if data.format:
            fmt = data.format
    elif isinstance(data, (bytes, bytearray)):
        raw_bytes = bytes(data)
    else:
        return ValidationResult(
            valid=False,
            format=fmt,
            checks_performed=checks,
            errors=[f"Invalid input type: {type(data)}. Expected bytes or RecoveredArtifact."],
        )

    # 1. Non-empty check
    if len(raw_bytes) == 0:
        errors.append("Artifact bytes are empty")
        return ValidationResult(
            valid=False,
            format=fmt,
            checks_performed=checks,
            errors=errors,
        )

    # Check for synthetic markers
    start_pos = raw_bytes.find(SYNTHETIC_START_MARKER)
    end_pos = raw_bytes.find(SYNTHETIC_END_MARKER)

    body_bytes = raw_bytes

    if start_pos != -1 or end_pos != -1:
        checks.extend(["start_marker_exists", "end_marker_exists", "marker_ordering"])
        if start_pos == -1:
            errors.append(f"Missing synthetic start marker: {SYNTHETIC_START_MARKER.decode('utf-8', errors='replace')}")
        if end_pos == -1:
            errors.append(f"Missing synthetic end marker: {SYNTHETIC_END_MARKER.decode('utf-8', errors='replace')}")
        if start_pos != -1 and end_pos != -1:
            if start_pos >= end_pos:
                errors.append(
                    f"Invalid marker ordering: start marker at offset {start_pos} "
                    f"occurs at or after end marker at offset {end_pos}"
                )
            else:
                body_start = start_pos + len(SYNTHETIC_START_MARKER)
                body_bytes = raw_bytes[body_start:end_pos]

    # UTF-8 decoding check
    try:
        text = body_bytes.decode("utf-8")
        if "\x00" in text:
            errors.append("Text content contains binary null bytes")
        # Line count covers the full artifact (including markers) for consistency
        full_text = raw_bytes.decode("utf-8")
        details["line_count"] = len(full_text.splitlines())
        details["char_count"] = len(text)
    except UnicodeDecodeError as e:
        errors.append(f"UTF-8 decoding failed: {e}")

    valid = len(errors) == 0
    return ValidationResult(
        valid=valid,
        format=fmt,
        checks_performed=checks,
        errors=errors,
        warnings=warnings,
        details=details,
    )
