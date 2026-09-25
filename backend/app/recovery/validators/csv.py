"""
csv.py — Deterministic CSV artifact structural validator.

Validates recovered CSV artifact bytes against synthetic harness boundaries,
UTF-8 encoding, Python csv module parsing rules, and row structural consistency.
"""

from __future__ import annotations

import csv
import io
from typing import Union, Any

from backend.app.models.validation import ValidationResult
from backend.app.recovery.carver import RecoveredArtifact
from backend.app.recovery.signatures import (
    SYNTHETIC_START_MARKER,
    SYNTHETIC_END_MARKER,
)


def validate_csv(data: bytes | RecoveredArtifact) -> ValidationResult:
    """Validate the structural integrity of a recovered CSV artifact.

    Accepts raw bytes or a RecoveredArtifact object.

    Checks performed:
      1. input_type: input is bytes (or RecoveredArtifact yielding bytes)
      2. non_empty: input is non-empty
      3. start_marker_exists: SYNTHETIC_START_MARKER is present
      4. end_marker_exists: SYNTHETIC_END_MARKER is present
      5. marker_ordering: start marker occurs before end marker
      6. utf8_decoding: payload can be safely decoded as UTF-8
      7. csv_parsing: body between markers parses successfully with csv.reader
      8. row_consistency: all non-empty rows have a consistent column count

    Args:
        data: Raw evidence bytes or RecoveredArtifact.

    Returns:
        ValidationResult with validation outcome, checks, errors, and details.
    """
    checks: list[str] = [
        "input_type",
        "non_empty",
        "start_marker_exists",
        "end_marker_exists",
        "marker_ordering",
        "utf8_decoding",
        "csv_parsing",
        "row_consistency",
    ]
    errors: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {}

    raw_bytes: bytes
    fmt: str = "csv"
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

    # 2. Start marker check
    start_pos = raw_bytes.find(SYNTHETIC_START_MARKER)
    if start_pos == -1:
        errors.append(f"Missing synthetic start marker: {SYNTHETIC_START_MARKER.decode('utf-8', errors='replace')}")

    # 3. End marker check
    end_pos = raw_bytes.find(SYNTHETIC_END_MARKER)
    if end_pos == -1:
        errors.append(f"Missing synthetic end marker: {SYNTHETIC_END_MARKER.decode('utf-8', errors='replace')}")

    # 4. Marker ordering check
    if start_pos != -1 and end_pos != -1:
        if start_pos >= end_pos:
            errors.append(
                f"Invalid marker ordering: start marker at offset {start_pos} "
                f"occurs at or after end marker at offset {end_pos}"
            )

    # If markers are valid, extract body and parse CSV
    if start_pos != -1 and end_pos != -1 and start_pos < end_pos:
        body_start = start_pos + len(SYNTHETIC_START_MARKER)
        body_bytes = raw_bytes[body_start:end_pos]

        # 5. UTF-8 decoding check
        try:
            body_text = body_bytes.decode("utf-8")
        except UnicodeDecodeError as e:
            errors.append(f"UTF-8 decoding failed: {e}")
            return ValidationResult(
                valid=False,
                format=fmt,
                checks_performed=checks,
                errors=errors,
                warnings=warnings,
                details=details,
            )

        # 6. CSV parsing check
        try:
            f = io.StringIO(body_text)
            reader = csv.reader(f)
            rows = [row for row in reader if any(field.strip() for field in row)]
            details["row_count"] = len(rows)

            if len(rows) == 0:
                errors.append("CSV body contains no data rows")
            else:
                # 7. Row consistency check
                col_counts = [len(row) for row in rows]
                details["column_counts"] = col_counts
                first_count = col_counts[0]
                if any(c != first_count for c in col_counts):
                    errors.append(f"Inconsistent row structure: column counts vary across rows ({col_counts})")
        except csv.Error as e:
            errors.append(f"CSV parsing failed: {e}")
        except Exception as e:
            errors.append(f"Unexpected error during CSV parsing: {e}")

    valid = len(errors) == 0
    return ValidationResult(
        valid=valid,
        format=fmt,
        checks_performed=checks,
        errors=errors,
        warnings=warnings,
        details=details,
    )
