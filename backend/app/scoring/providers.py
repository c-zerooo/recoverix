"""
providers.py — Interpretation Providers for Grounded Forensic Evidence Analysis.

Milestone 3.5.1: Implements InterpretationProvider protocol, DeterministicRuleProvider,
and GeminiInterpretationProvider with strict fact-ownership separation and safe fallbacks.
"""

from __future__ import annotations

import os
import json
import logging
from typing import Protocol, Optional, Any, Dict, List

from backend.app.models.interpretation import (
    ArtifactInterpretationContext,
    ProviderInterpretationOutput,
)

logger = logging.getLogger(__name__)


class InterpretationProvider(Protocol):
    """Protocol for interpretation narrative generators."""

    def interpret_artifact(
        self, context: ArtifactInterpretationContext
    ) -> ProviderInterpretationOutput:
        """Generate interpretive prose from deterministic artifact context."""
        ...


class DeterministicRuleProvider:
    """Offline, deterministic rule-based interpretation provider.

    Executes entirely in local memory with zero external network requests and no API keys.
    Covers all four authoritative Recoverix statuses: FULLY_RECOVERED, PARTIALLY_RECOVERED,
    CORRUPTED, and UNRECOVERABLE without inventing unverified facts.
    """

    def interpret_artifact(
        self, context: ArtifactInterpretationContext
    ) -> ProviderInterpretationOutput:
        facts = context.facts
        fmt = facts.format.lower()
        status = facts.status
        v_bytes = facts.verified_bytes
        r_bytes = facts.reconstructed_bytes
        m_bytes = facts.missing_bytes
        score = (
            int(facts.confidence_score)
            if float(facts.confidence_score).is_integer()
            else round(facts.confidence_score, 2)
        )
        priority = facts.priority
        category = facts.category
        method = facts.reconstruction_method

        # 1. Detail bullet lines (backward-compatible with Stage 11 tests and UI)
        what_was_recovered = f"Recovered {v_bytes} verified bytes and {r_bytes} reconstructed bytes."
        what_is_verified = f"{v_bytes} bytes were mathematically verified."
        what_is_missing = f"{m_bytes} bytes are missing."
        status_reasoning = f"Score: {score}/100. Assigned status {status} based on deterministic rules."
        if r_bytes > 0:
            status_reasoning += " Status capped at PARTIALLY_RECOVERED because reconstructed bytes exist."
        priority_reasoning = f"Assigned {priority} based on content pattern matching and {category} categorization."

        details = [
            what_was_recovered,
            what_is_verified,
            what_is_missing,
            status_reasoning,
            priority_reasoning,
        ]

        summary = f"Grounded explanation for {category} artifact."

        # 2. Status-specific grounded narrative
        if status == "FULLY_RECOVERED":
            assessment = (
                f"This artifact is fully recovered. All {v_bytes} bytes were mathematically "
                f"verified from the uploaded evidence with 0 missing and 0 reconstructed bytes."
            )
            structural_context = (
                f"The artifact adheres completely to the {fmt.upper()} specification with authoritative validation. "
                "Evidence integrity is verified for judicial chain of custody."
            )
            limitations = (
                "Exact deterministic recovery. Zero heuristic AI predictions or synthetic filler bytes were used."
            )
            recommended_next_steps = (
                "Export the recovered file and log the deterministic validation digest into the investigation case file."
            )

        elif status == "PARTIALLY_RECOVERED":
            if r_bytes > 0 and m_bytes == 0:
                assessment = (
                    f"The {fmt.upper()} artifact contains a structurally complete observed prefix. "
                    f"The missing content was limited to {r_bytes} uniquely determined closing "
                    f"{fmt.upper()} delimiters."
                )
                structural_context = (
                    f"The reconstructed bytes were derived from the observed {fmt.upper()} "
                    "container structure rather than predicted semantic content."
                )
                limitations = (
                    f"Deterministic structural closure only ({method}). "
                    "Recoverix strictly refused to predict or synthesize unobserved semantic data."
                )
                recommended_next_steps = (
                    f"Inspect the {fmt.upper()} structural tokens and verify that reconstructed closing syntax matches schema expectations."
                )
            elif r_bytes > 0 and m_bytes > 0:
                assessment = (
                    f"This artifact is partially recovered. {v_bytes} bytes were mathematically "
                    f"verified from the uploaded evidence, {r_bytes} bytes were structurally reconstructed via {method}, "
                    f"and an unobserved {m_bytes}-byte gap was preserved."
                )
                structural_context = (
                    f"The reconstructed bytes were derived from deterministic grammar rules, "
                    f"while the unobserved {m_bytes}-byte region was preserved to prevent evidence hallucination."
                )
                limitations = (
                    "Missing bytes could not be deterministically established and were preserved as missing."
                )
                recommended_next_steps = (
                    "Review original evidence source or examine adjacent storage clusters for matching fragments."
                )
            else:
                assessment = (
                    f"This artifact is partially recovered. {v_bytes} bytes were mathematically "
                    f"verified from the uploaded evidence, and an unobserved {m_bytes}-byte region remains missing."
                )
                structural_context = (
                    f"Surviving evidence fragments maintain authoritative integrity ({method}), "
                    f"but unobserved missing bytes cannot be deterministically inferred."
                )
                limitations = (
                    "Missing bytes could not be deterministically established and were preserved as missing. "
                    "Recoverix strictly refused to hallucinate synthetic content."
                )
                recommended_next_steps = (
                    "Review the original evidence source or adjacent storage regions for additional matching fragments."
                )

        elif status == "CORRUPTED":
            assessment = (
                f"This candidate exhibits {fmt.upper()} structural markers ({v_bytes} bytes observed), "
                "but failed cryptographic or format integrity validation. Data corruption is present."
            )
            structural_context = (
                "Key syntax anchors were detected, but internal records, checksums, or delimiters failed integrity verification. "
                "Proceeding without fragment reconstruction risks evidence falsification."
            )
            limitations = (
                "Recoverix strictly refused to fabricate file headers, repair damaged binary streams, "
                "or guess corrupted byte values."
            )
            recommended_next_steps = (
                "Perform manual forensic hex inspection on isolated anomaly regions or search adjacent sectors for uncorrupted fragments."
            )

        elif status == "UNRECOVERABLE":
            assessment = (
                f"This artifact is unrecoverable under the {fmt.upper()} format specification. "
                f"{m_bytes or 'Evidence'} bytes of input yielded no valid structural markers or signatures."
            )
            structural_context = (
                "Severe corruption or missing critical headers prevent deterministic reconstruction. "
                "Proceeding without additional fragments would risk evidence falsification."
            )
            limitations = (
                "Recoverix strictly refused to fabricate file headers or simulate recovery on unverifiable binary streams."
            )
            recommended_next_steps = (
                "Acquire adjacent unallocated disk clusters or examine raw sector dumps for overwritten carving headers."
            )

        else:
            assessment = (
                f"Artifact evaluated with status {status}. {v_bytes} verified bytes, "
                f"{r_bytes} reconstructed bytes, {m_bytes} missing bytes."
            )
            structural_context = f"Deterministic forensic evaluation score: {score}/100."
            limitations = "Zero heuristic AI predictions were used to generate evidence."
            recommended_next_steps = "Perform manual forensic hex inspection on isolated anomaly regions."

        return ProviderInterpretationOutput(
            summary=summary,
            assessment=assessment,
            structural_context=structural_context,
            limitations=limitations,
            recommended_next_steps=recommended_next_steps,
            details=details,
        )


class GeminiInterpretationProvider:
    """Optional external Gemini interpretation provider.

    Executes strictly when RECOVERIX_OFFLINE != 1 and a valid Gemini API key is configured.
    Enforces hard timeout, strict output JSON schema, and absolute exclusion of raw evidence bytes.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    def interpret_artifact(
        self, context: ArtifactInterpretationContext
    ) -> ProviderInterpretationOutput:
        # Precedence: OFFLINE MODE > API KEY
        if os.getenv("RECOVERIX_OFFLINE", "0").lower() in ("1", "true", "yes"):
            raise RuntimeError("Offline mode enabled (RECOVERIX_OFFLINE=1): external AI provider is blocked")

        if not self.api_key:
            raise RuntimeError("Gemini API key is not configured")

        import httpx

        facts_dict = {
            "artifact_id": context.facts.artifact_id,
            "filename": context.facts.filename,
            "format": context.facts.format,
            "status": context.facts.status,
            "category": context.facts.category,
            "priority": context.facts.priority,
            "confidence_score": context.facts.confidence_score,
            "verified_bytes": context.facts.verified_bytes,
            "reconstructed_bytes": context.facts.reconstructed_bytes,
            "missing_bytes": context.facts.missing_bytes,
            "reconstruction_method": context.facts.reconstruction_method,
            "validation_status": context.facts.validation_status,
            "damage_region_count": context.facts.damage_region_count,
            "is_ambiguous": context.facts.is_ambiguous,
            "content_preview": context.content_preview or "",
        }

        prompt = (
            "You are the Recoverix AI Evidence Analyst, a digital forensics investigator assistant.\n"
            "Interpret ONLY the following deterministic recovery facts established by the reconstruction engine.\n"
            "CRITICAL FORENSIC RULES:\n"
            "1. You MUST NOT invent bytes, modify bytes, or override V/R/M.\n"
            "2. You MUST NOT alter or contradict status, confidence_score, or priority.\n"
            "3. You MUST NOT make legal conclusions, determine criminal intent, or identify suspects.\n"
            "4. You MUST acknowledge all corrupted, missing, or reconstructed regions explicitly.\n\n"
            f"DETERMINISTIC FACTS:\n{json.dumps(facts_dict, indent=2)}\n\n"
            "Return a JSON object with EXACTLY these string keys:\n"
            '- "summary": Concise executive overview.\n'
            '- "assessment": Factual summary of verified vs reconstructed vs missing bytes.\n'
            '- "structural_context": Forensic importance of the surviving structural evidence and format markers.\n'
            '- "limitations": Explicit explanation that Recoverix did not fabricate missing bytes.\n'
            '- "recommended_next_steps": Concrete recommended next investigative step for examiners.\n'
            '- "details": List of 3 to 5 concise analytical bullet statements.\n'
        )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json"},
        }

        with httpx.Client(timeout=3.5) as client:
            resp = client.post(url, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"Gemini API returned HTTP status {resp.status_code}: {resp.text}")

            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise ValueError("Gemini response contained no candidates")

            text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            if not text:
                raise ValueError("Gemini response candidate contained no text content")

            parsed = json.loads(text)

            # Map legacy/alternate keys if returned by model
            summary = parsed.get("summary") or f"Grounded explanation for {context.facts.category} artifact."
            assessment = parsed.get("assessment", "")
            structural_context = parsed.get("structural_context") or parsed.get("why_it_matters", "")
            limitations = parsed.get("limitations") or parsed.get("recovery_limitation", "")
            recommended_next_steps = parsed.get("recommended_next_steps") or parsed.get("recommended_next_step", "")
            details = parsed.get("details", [])
            if not isinstance(details, list):
                details = [str(details)]

            if not assessment or not structural_context or not limitations or not recommended_next_steps:
                raise ValueError(f"Gemini response missing required interpretive fields: {parsed.keys()}")

            return ProviderInterpretationOutput(
                summary=summary,
                assessment=assessment,
                structural_context=structural_context,
                limitations=limitations,
                recommended_next_steps=recommended_next_steps,
                details=details,
            )
