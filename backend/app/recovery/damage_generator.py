"""
damage_generator.py — Controlled deterministic damage operations and fixture generator.

Creates reproducible, forensic-grade corruption scenarios for automated testing
across all supported formats. Each scenario records:
  - original bytes + SHA-256
  - damaged bytes + SHA-256
  - damage offset & length
  - damage type
  - expected recoverability & exactness
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple

from backend.app.recovery.signatures import (
    SYNTHETIC_START_MARKER,
    SYNTHETIC_END_MARKER,
)


@dataclass(frozen=True)
class DamageScenario:
    """A deterministic damage test scenario with full ground-truth tracking."""

    scenario_id: str
    format: str
    description: str
    original_bytes: bytes
    damaged_bytes: bytes
    original_sha256: str
    damaged_sha256: str
    damage_type: str
    damage_offset: int
    damage_length: int
    expected_recoverability: bool
    expected_exact_sha: bool
    metadata: Dict[str, Any]


# ── Damage Primitive Operations ─────────────────────────────────────────────

def apply_deletion(data: bytes, offset: int, length: int) -> Tuple[bytes, int, int]:
    """Delete a range of *length* bytes starting at *offset*."""
    if offset < 0 or offset > len(data):
        raise ValueError(f"Offset {offset} out of bounds for data length {len(data)}")
    actual_len = min(length, len(data) - offset)
    mutated = data[:offset] + data[offset + actual_len:]
    return mutated, offset, actual_len


def apply_zero_fill(data: bytes, offset: int, length: int) -> Tuple[bytes, int, int]:
    """Overwrite *length* bytes starting at *offset* with null bytes (0x00)."""
    if offset < 0 or offset > len(data):
        raise ValueError(f"Offset {offset} out of bounds for data length {len(data)}")
    actual_len = min(length, len(data) - offset)
    mutated = data[:offset] + (b"\x00" * actual_len) + data[offset + actual_len:]
    return mutated, offset, actual_len


def apply_overwrite(data: bytes, offset: int, replacement: bytes) -> Tuple[bytes, int, int]:
    """Overwrite bytes at *offset* with *replacement*."""
    if offset < 0 or offset > len(data):
        raise ValueError(f"Offset {offset} out of bounds for data length {len(data)}")
    actual_len = min(len(replacement), len(data) - offset)
    mutated = data[:offset] + replacement[:actual_len] + data[offset + actual_len:]
    return mutated, offset, actual_len


def apply_truncation(data: bytes, remaining_length: int) -> Tuple[bytes, int, int]:
    """Truncate *data* to *remaining_length* bytes."""
    if remaining_length < 0 or remaining_length > len(data):
        raise ValueError(f"remaining_length {remaining_length} out of bounds")
    truncated_len = len(data) - remaining_length
    return data[:remaining_length], remaining_length, truncated_len


# ── Text & CSV Fixture Builders ─────────────────────────────────────────────

def get_txt_scenarios() -> List[DamageScenario]:
    """Build controlled, reproducible TXT damage test scenarios."""
    scenarios: List[DamageScenario] = []

    # 1. Intact TXT
    orig1 = (
        b"Recoverix Digital Forensics Report\n"
        b"Case ID: CASE-2026-0926-A\n"
        b"Investigator: Special Agent Antigravity\n"
        b"Evidence Status: Authentic and Intact.\n"
        b"All systems nominal.\n"
    )
    scenarios.append(
        DamageScenario(
            scenario_id="txt_01_intact",
            format="txt",
            description="Intact standard UTF-8 text document",
            original_bytes=orig1,
            damaged_bytes=orig1,
            original_sha256=hashlib.sha256(orig1).hexdigest(),
            damaged_sha256=hashlib.sha256(orig1).hexdigest(),
            damage_type="NONE",
            damage_offset=0,
            damage_length=0,
            expected_recoverability=True,
            expected_exact_sha=True,
            metadata={"lines": 5},
        )
    )

    # 2. Truncated mid-multibyte UTF-8 character
    # "Financial Record: Transaction €500.00" -> € is \xe2\x82\xac (3 bytes)
    full_text = "Financial Audit: Total transaction amount was 1500 €".encode("utf-8")
    # Truncate after first 2 bytes of the euro symbol
    cut_point = len(full_text) - 1  # leaves \xe2\x82 without \xac
    damaged_trunc, off, length = apply_truncation(full_text, cut_point)
    scenarios.append(
        DamageScenario(
            scenario_id="txt_02_truncated_utf8",
            format="txt",
            description="TXT truncated mid-sequence inside 3-byte UTF-8 symbol",
            original_bytes=full_text,
            damaged_bytes=damaged_trunc,
            original_sha256=hashlib.sha256(full_text).hexdigest(),
            damaged_sha256=hashlib.sha256(damaged_trunc).hexdigest(),
            damage_type="TRUNCATED_UTF8",
            damage_offset=off,
            damage_length=length,
            expected_recoverability=True,
            expected_exact_sha=False,  # Truncated code point cannot be invented
            metadata={"truncated_bytes": length},
        )
    )

    # 3. Middle region null byte injection
    orig3 = (
        b"Section 1: Initial Findings and System Audit Logs.\n"
        b"Section 2: Critical forensic telemetry data from server 01.\n"
        b"Section 3: Incident response timeline and conclusion.\n"
    )
    # Zero-fill 40 bytes in the middle of Section 2
    damaged3, off3, len3 = apply_zero_fill(orig3, 60, 40)
    scenarios.append(
        DamageScenario(
            scenario_id="txt_03_middle_null_corruption",
            format="txt",
            description="TXT with 40-byte zero-fill corruption in middle section",
            original_bytes=orig3,
            damaged_bytes=damaged3,
            original_sha256=hashlib.sha256(orig3).hexdigest(),
            damaged_sha256=hashlib.sha256(damaged3).hexdigest(),
            damage_type="ZERO_FILL",
            damage_offset=off3,
            damage_length=len3,
            expected_recoverability=True,
            expected_exact_sha=False,
            metadata={"null_count": len3},
        )
    )

    # 4. Fragmented TXT with gap
    frag_a = b"Subject: Incident Escalation\nTo: Security Operations Center\n\n"
    frag_b = b"Action Taken: Contained infected workstation and quarantined IP.\n"
    full_orig4 = frag_a + b"Details: Ransomware payload was executed at 03:14:02 UTC.\n" + frag_b
    gap_bytes = b"\x00" * 48
    damaged_frag = frag_a + gap_bytes + frag_b
    scenarios.append(
        DamageScenario(
            scenario_id="txt_04_fragmented_gap",
            format="txt",
            description="Two intact TXT fragments separated by an unobserved 48-byte gap",
            original_bytes=full_orig4,
            damaged_bytes=damaged_frag,
            original_sha256=hashlib.sha256(full_orig4).hexdigest(),
            damaged_sha256=hashlib.sha256(damaged_frag).hexdigest(),
            damage_type="BOUNDED_GAP",
            damage_offset=len(frag_a),
            damage_length=len(gap_bytes),
            expected_recoverability=True,
            expected_exact_sha=False,
            metadata={"gap_size": len(gap_bytes)},
        )
    )

    # 5. Missing synthetic end marker (recoverable structural repair)
    clean_payload = b"FORMAT=txt\nHeader: Incident Notes\nContent: Evidence preserved in vault.\n"
    orig5 = SYNTHETIC_START_MARKER + clean_payload + SYNTHETIC_END_MARKER
    damaged5 = SYNTHETIC_START_MARKER + clean_payload  # missing end marker
    scenarios.append(
        DamageScenario(
            scenario_id="txt_05_missing_synthetic_marker",
            format="txt",
            description="TXT wrapped in synthetic markers with truncated end marker",
            original_bytes=orig5,
            damaged_bytes=damaged5,
            original_sha256=hashlib.sha256(orig5).hexdigest(),
            damaged_sha256=hashlib.sha256(damaged5).hexdigest(),
            damage_type="MISSING_SYNTHETIC_FOOTER",
            damage_offset=len(damaged5),
            damage_length=len(SYNTHETIC_END_MARKER),
            expected_recoverability=True,
            expected_exact_sha=True,  # Synthetic marker restored deterministically
            metadata={"reconstructed_marker": "SYNTHETIC_END_MARKER"},
        )
    )

    # 6. Unrecoverable high-entropy random binary noise
    rng = random.Random(42)
    garbage_bytes = bytes(rng.randint(0, 255) for _ in range(128))
    scenarios.append(
        DamageScenario(
            scenario_id="txt_06_unrecoverable_garbage",
            format="txt",
            description="Pure random high-entropy binary noise",
            original_bytes=garbage_bytes,
            damaged_bytes=garbage_bytes,
            original_sha256=hashlib.sha256(garbage_bytes).hexdigest(),
            damaged_sha256=hashlib.sha256(garbage_bytes).hexdigest(),
            damage_type="BINARY_GARBAGE",
            damage_offset=0,
            damage_length=len(garbage_bytes),
            expected_recoverability=False,
            expected_exact_sha=False,
            metadata={"entropy": "high"},
        )
    )

    return scenarios


def get_csv_scenarios() -> List[DamageScenario]:
    """Build controlled, reproducible CSV damage test scenarios."""
    scenarios: List[DamageScenario] = []

    # 1. Intact CSV
    orig1 = (
        b"id,name,role,department\n"
        b"1,Alice,Admin,Security\n"
        b"2,Bob,Analyst,Forensics\n"
        b"3,Charlie,Engineer,Infrastructure\n"
        b"4,Diana,Auditor,Compliance\n"
    )
    scenarios.append(
        DamageScenario(
            scenario_id="csv_01_intact",
            format="csv",
            description="Intact 4-column CSV with 4 data rows",
            original_bytes=orig1,
            damaged_bytes=orig1,
            original_sha256=hashlib.sha256(orig1).hexdigest(),
            damaged_sha256=hashlib.sha256(orig1).hexdigest(),
            damage_type="NONE",
            damage_offset=0,
            damage_length=0,
            expected_recoverability=True,
            expected_exact_sha=True,
            metadata={"rows": 5, "columns": 4},
        )
    )

    # 2. Truncated final row
    orig2 = (
        b"id,hostname,ip_address,status\n"
        b"101,server-alpha,10.0.0.1,ACTIVE\n"
        b"102,server-beta,10.0.0.2,ACTIVE\n"
        b"103,server-gamma,10.0.0.3,SUSPENDED\n"
    )
    # Truncate last row mid-field to: "103,server-gam"
    damaged2 = (
        b"id,hostname,ip_address,status\n"
        b"101,server-alpha,10.0.0.1,ACTIVE\n"
        b"102,server-beta,10.0.0.2,ACTIVE\n"
        b"103,server-gam"
    )
    scenarios.append(
        DamageScenario(
            scenario_id="csv_02_truncated_final_row",
            format="csv",
            description="CSV truncated mid-field in final data row",
            original_bytes=orig2,
            damaged_bytes=damaged2,
            original_sha256=hashlib.sha256(orig2).hexdigest(),
            damaged_sha256=hashlib.sha256(damaged2).hexdigest(),
            damage_type="TRUNCATED_FINAL_ROW",
            damage_offset=len(damaged2),
            damage_length=len(orig2) - len(damaged2),
            expected_recoverability=True,
            expected_exact_sha=False,  # Dropped partial record cannot be guessed
            metadata={"intact_rows": 2},
        )
    )

    # 3. Unclosed quoted field repair
    damaged3_unclosed = (
        b"id,name,notes\n"
        b"1,Alice,OK\n"
        b"2,Bob,\"Special Account Notes, Priority Client"
    )
    orig3 = (
        b"id,name,notes\n"
        b"1,Alice,OK\n"
        b"2,Bob,\"Special Account Notes, Priority Client\"\n"
    )
    scenarios.append(
        DamageScenario(
            scenario_id="csv_03_unclosed_quote_repair",
            format="csv",
            description="CSV with unclosed quote on final row deterministically closed",
            original_bytes=orig3,
            damaged_bytes=damaged3_unclosed,
            original_sha256=hashlib.sha256(orig3).hexdigest(),
            damaged_sha256=hashlib.sha256(damaged3_unclosed).hexdigest(),
            damage_type="UNCLOSED_QUOTE",
            damage_offset=len(damaged3_unclosed),
            damage_length=2,
            expected_recoverability=True,
            expected_exact_sha=True,  # Closing quote and newline deterministically restored
            metadata={"repair": "quote_close"},
        )
    )

    # 4. Damaged middle row (inconsistent column count / delimiter corruption)
    orig4 = (
        b"emp_id,first_name,last_name,department\n"
        b"1001,John,Doe,Finance\n"
        b"1002,Jane,Smith,Engineering\n"
        b"1003,Robert,Johnson,Operations\n"
        b"1004,Emily,Davis,Legal\n"
    )
    # Corrupt row 3 to have 6 columns instead of 4: "1003,Robert,X,Y,Z,Johnson\n"
    damaged4 = (
        b"emp_id,first_name,last_name,department\n"
        b"1001,John,Doe,Finance\n"
        b"1002,Jane,Smith,Engineering\n"
        b"1003,Robert,CORRUPT,DELIMITERS,EXTRA,Johnson\n"
        b"1004,Emily,Davis,Legal\n"
    )
    scenarios.append(
        DamageScenario(
            scenario_id="csv_04_damaged_middle_row",
            format="csv",
            description="CSV with corrupted middle row (inconsistent column count)",
            original_bytes=orig4,
            damaged_bytes=damaged4,
            original_sha256=hashlib.sha256(orig4).hexdigest(),
            damaged_sha256=hashlib.sha256(damaged4).hexdigest(),
            damage_type="INCONSISTENT_ROW_COLUMNS",
            damage_offset=len(b"emp_id,first_name,last_name,department\n1001,John,Doe,Finance\n1002,Jane,Smith,Engineering\n"),
            damage_length=len(b"1003,Robert,CORRUPT,DELIMITERS,EXTRA,Johnson\n"),
            expected_recoverability=True,
            expected_exact_sha=False,  # Inconsistent row dropped
            metadata={"expected_cols": 4, "bad_cols": 6},
        )
    )

    # 5. Missing trailing newline (pure structural repair)
    orig5 = b"id,val\n1,one\n2,two\n"
    damaged5 = b"id,val\n1,one\n2,two"  # no trailing newline
    scenarios.append(
        DamageScenario(
            scenario_id="csv_05_missing_trailing_newline",
            format="csv",
            description="CSV missing standard trailing newline terminator",
            original_bytes=orig5,
            damaged_bytes=damaged5,
            original_sha256=hashlib.sha256(orig5).hexdigest(),
            damaged_sha256=hashlib.sha256(damaged5).hexdigest(),
            damage_type="MISSING_TRAILING_NEWLINE",
            damage_offset=len(damaged5),
            damage_length=1,
            expected_recoverability=True,
            expected_exact_sha=True,  # Newline is restored
            metadata={"structural_addition": 1},
        )
    )

    # 6. Fragmented CSV across missing row gap
    header_and_r1 = b"user_id,username,email,role\n1,user1,u1@corp.net,USER\n2,user2,u2@corp.net,USER\n"
    tail_rows = b"5,user5,u5@corp.net,ADMIN\n6,user6,u6@corp.net,DEV\n"
    full_orig6 = header_and_r1 + b"3,user3,u3@corp.net,USER\n4,user4,u4@corp.net,USER\n" + tail_rows
    gap6 = b"\x00" * 64
    damaged6 = header_and_r1 + gap6 + tail_rows
    scenarios.append(
        DamageScenario(
            scenario_id="csv_06_fragmented_gap",
            format="csv",
            description="Two intact CSV fragments separated by 64-byte gap (missing rows)",
            original_bytes=full_orig6,
            damaged_bytes=damaged6,
            original_sha256=hashlib.sha256(full_orig6).hexdigest(),
            damaged_sha256=hashlib.sha256(damaged6).hexdigest(),
            damage_type="BOUNDED_GAP",
            damage_offset=len(header_and_r1),
            damage_length=len(gap6),
            expected_recoverability=True,
            expected_exact_sha=False,
            metadata={"gap_size": len(gap6)},
        )
    )

    # 7. Unrecoverable binary non-CSV
    rng = random.Random(99)
    binary_noise = bytes(rng.randint(0, 255) for _ in range(150))
    scenarios.append(
        DamageScenario(
            scenario_id="csv_07_unrecoverable_binary",
            format="csv",
            description="Binary random data with no CSV rows or delimiter structure",
            original_bytes=binary_noise,
            damaged_bytes=binary_noise,
            original_sha256=hashlib.sha256(binary_noise).hexdigest(),
            damaged_sha256=hashlib.sha256(binary_noise).hexdigest(),
            damage_type="BINARY_GARBAGE",
            damage_offset=0,
            damage_length=len(binary_noise),
            expected_recoverability=False,
            expected_exact_sha=False,
            metadata={"valid": False},
        )
    )

    return scenarios
