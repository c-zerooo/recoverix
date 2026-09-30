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
    ClusterInterpretationContext,
    CaseInterpretationContext,
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

    def interpret_cluster(
        self, context: ClusterInterpretationContext
    ) -> ProviderInterpretationOutput:
        """Generate interpretive prose from deterministic cluster context."""
        ...

    def interpret_case(
        self, context: CaseInterpretationContext
    ) -> ProviderInterpretationOutput:
        """Generate executive forensic briefing prose from deterministic case context."""
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

    def interpret_cluster(
        self, context: ClusterInterpretationContext
    ) -> ProviderInterpretationOutput:
        facts = context.facts
        rel_class = facts.relationship_classification
        total_nodes = facts.total_nodes
        formats_str = ", ".join(facts.member_formats) if facts.member_formats else "unknown"
        v_bytes = facts.candidate_aggregate_verified_bytes
        r_bytes = facts.candidate_aggregate_reconstructed_bytes
        m_bytes = facts.candidate_aggregate_missing_bytes
        u_bytes = facts.unique_physical_bytes
        b_bytes = facts.bounded_physical_bytes
        max_score = (
            int(facts.max_confidence_score)
            if float(facts.max_confidence_score).is_integer()
            else round(facts.max_confidence_score, 2)
        )
        priority = facts.highest_priority
        c_start = facts.cluster_start
        c_end = facts.cluster_end

        # Details list
        if u_bytes is not None:
            footprint_detail = f"Physical Evidence Footprint: {u_bytes} unique bytes across coordinate envelope [{c_start}, {c_end})."
        else:
            footprint_detail = f"Physical Evidence Footprint: Unbounded candidate span (lower bound: {b_bytes} bounded bytes from offset {c_start})."

        volume_detail = (
            f"Candidate Evaluation Volume: {v_bytes} verified bytes, {r_bytes} reconstructed bytes, "
            f"{m_bytes} missing bytes across {total_nodes} candidate interpretation(s)."
        )
        classification_detail = f"Spatial Classification: {rel_class} across format(s): {formats_str}."
        status_items = [f"{k}: {v}" for k, v in sorted(facts.status_distribution.items())]
        status_detail = f"Recovery Status Distribution: {', '.join(status_items) or 'None'}."
        priority_detail = f"Cluster Priority: {priority} (Max Confidence Score: {max_score}/100)."

        details = [
            footprint_detail,
            volume_detail,
            classification_detail,
            status_detail,
            priority_detail,
        ]

        summary = f"Grounded cluster synthesis for {rel_class} spatial component ({total_nodes} candidate{'s' if total_nodes > 1 else ''})."

        # Classification-specific grounded narrative
        if rel_class == "ISOLATED":
            if total_nodes == 1:
                assessment = (
                    f"Single isolated candidate ({formats_str}) spanning "
                    f"{u_bytes if u_bytes is not None else 'unbounded'} physical bytes. "
                    "No spatial overlap or candidate competition detected."
                )
            else:
                assessment = (
                    f"Isolated candidate set spanning "
                    f"{u_bytes if u_bytes is not None else 'unbounded'} physical bytes "
                    "with no internal spatial overlap edges."
                )
            structural_context = (
                "Uncontested extraction. Structural markers and validation proofs establish standalone artifact boundaries without conflicting interpretations."
            )
            limitations = (
                "Standard deterministic boundary extraction. Zero heuristic spatial assumptions or speculative joins were applied."
            )
            recommended_next_steps = (
                "Verify individual artifact validation status and integrate verified output into the investigation case file."
            )

        elif rel_class == "COEXTENSIVE_SET":
            assessment = (
                f"Direct competing format hypotheses over identical physical byte range [{c_start}, {c_end}). "
                f"{total_nodes} candidate interpretations ({formats_str}) evaluate the same {u_bytes} physical bytes."
            )
            structural_context = (
                f"Candidates occupy coextensive coordinates. Recoverix preserves all {total_nodes} competing format interpretations neutrally rather than arbitrarily declaring a single winning format."
            )
            limitations = (
                f"Candidate aggregate volume ({v_bytes} verified bytes) reflects multiple format evaluations and must NOT be treated as {v_bytes} physical disk bytes. Physical footprint is strictly {u_bytes} bytes."
            )
            recommended_next_steps = (
                f"Compare validation proofs and format-specific delimiter markers between competing formats ({formats_str}) to determine primary forensic interpretation."
            )

        elif rel_class == "CONTAINMENT_TREE":
            c_edges = facts.containment_edge_count
            assessment = (
                f"Hierarchical structural containment detected ({c_edges} containment edge{'s' if c_edges != 1 else ''}). "
                f"Outer container encompasses inner candidate payload(s) across a {u_bytes if u_bytes is not None else 'unbounded'}-byte physical span."
            )
            structural_context = (
                f"Container-payload encapsulation across formats ({formats_str}). Embedded inner artifacts represent nested payloads rather than competing format hypotheses."
            )
            limitations = (
                f"Candidate aggregate verified volume ({v_bytes} bytes) counts both enclosing container and inner payload bytes. Physical storage footprint is {u_bytes if u_bytes is not None else 'unbounded'} bytes."
            )
            recommended_next_steps = (
                "Inspect the outer container structure and extract verified inner payloads for independent forensic validation."
            )

        elif rel_class == "OVERLAP_SPAN":
            o_edges = facts.overlap_edge_count
            assessment = (
                f"Spatial boundary conflict detected ({o_edges} overlap edge{'s' if o_edges != 1 else ''}) across {total_nodes} candidates ({formats_str}) occupying a {u_bytes if u_bytes is not None else 'unbounded'}-byte union."
            )
            structural_context = (
                "Partial coordinate intersection indicates possible filesystem fragmentation, cluster slack re-allocation, or sliding-window boundary collisions."
            )
            limitations = (
                "Recoverix strictly refused to guess whether overlapping bytes represent fragmentation or carving false positives. Both candidate spans were preserved."
            )
            recommended_next_steps = (
                "Conduct hex inspection on the intersection byte regions to verify sector boundary alignments and fragment continuity."
            )

        elif rel_class == "MIXED":
            assessment = (
                f"Complex hybrid spatial topology exhibiting multiple relationship families "
                f"({facts.containment_edge_count} containment, {facts.overlap_edge_count} overlap, {facts.coextensive_candidate_count} coextensive) across {total_nodes} nodes."
            )
            structural_context = (
                f"Multi-candidate relationship graph spanning formats ({formats_str}). Combines structural encapsulation and partial boundary overlaps."
            )
            limitations = (
                "Complex graph topology with high structural ambiguity. Candidate aggregate volume does not reflect physical disk recovery."
            )
            recommended_next_steps = (
                "Perform detailed graph traversal and manual hex analysis across cluster junction boundaries."
            )

        else:
            assessment = f"Cluster evaluated with classification {rel_class}. {total_nodes} nodes across formats ({formats_str})."
            structural_context = f"Cluster priority: {priority} (Max confidence score: {max_score}/100)."
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

    def interpret_case(
        self, context: CaseInterpretationContext
    ) -> ProviderInterpretationOutput:
        facts = context.facts
        case_id = facts.case_id
        tot_buffers = facts.total_evidence_buffers
        tot_artifacts = facts.total_artifacts
        tot_nodes = facts.total_nodes
        tot_clusters = facts.total_clusters
        coverage_bytes = facts.case_physical_coverage_bytes
        v_bytes = facts.candidate_aggregate_verified_bytes
        r_bytes = facts.candidate_aggregate_reconstructed_bytes
        m_bytes = facts.candidate_aggregate_missing_bytes
        unscoped_count = facts.unscoped_candidate_count
        unscoped_v = facts.unscoped_aggregate_verified_bytes

        status_dist = facts.status_distribution
        priority_dist = facts.priority_distribution
        format_dist = facts.format_distribution
        cluster_dist = facts.cluster_classification_distribution

        # Details bullets
        coverage_str = f"{coverage_bytes} bytes" if coverage_bytes is not None else "Unbounded/Partial"
        coverage_detail = f"Physical Evidence Coverage: {coverage_str} across {tot_buffers} scoped buffer(s)."
        volume_detail = (
            f"Candidate Evaluation Volume: {v_bytes} verified bytes, {r_bytes} reconstructed bytes, "
            f"{m_bytes} missing bytes across {tot_artifacts} evaluated artifact(s)."
        )
        status_items = [f"{k}: {v}" for k, v in sorted(status_dist.items())]
        status_detail = f"Recovery Status Distribution: {', '.join(status_items) or 'None'}."

        cluster_items = [f"{k}: {v}" for k, v in sorted(cluster_dist.items())]
        cluster_detail = f"Cluster Classification Distribution: {', '.join(cluster_items) or 'None'}."

        format_items = [f"{k}: {v}" for k, v in sorted(format_dist.items())]
        format_detail = f"Format Breakdown: {', '.join(format_items) or 'None'}."

        details = [
            coverage_detail,
            volume_detail,
            status_detail,
            cluster_detail,
            format_detail,
        ]

        if facts.candidate_cap_enforced:
            details.append(
                f"Candidate Budget Cap: ENFORCED ({facts.candidates_omitted} candidate(s) omitted from analysis pool)."
            )
        if unscoped_count > 0:
            details.append(
                f"Unscoped Candidates: {unscoped_count} candidate(s) evaluated outside physical buffer coordinates ({unscoped_v} verified bytes)."
            )

        summary = (
            f"Executive forensic briefing for Case '{case_id}': {tot_nodes} candidate nodes analyzed "
            f"across {tot_clusters} spatial cluster(s) and {tot_buffers} evidence buffer(s)."
        )

        fully_rec = status_dist.get("FULLY_RECOVERED", 0)
        part_rec = status_dist.get("PARTIALLY_RECOVERED", 0)
        corr_rec = status_dist.get("CORRUPTED", 0)
        unrec_rec = status_dist.get("UNRECOVERABLE", 0)

        assessment = (
            f"Investigation case encompasses {tot_artifacts} total artifact(s) structured into {tot_clusters} spatial cluster(s). "
            f"Overall recovery health: {fully_rec} fully recovered, {part_rec} partially recovered, "
            f"{corr_rec} corrupted, and {unrec_rec} unrecoverable candidate(s)."
        )

        structural_context = (
            f"Evidence relationship graph spans {tot_buffers} evidence buffer(s) and {tot_nodes} graph nodes. "
            f"Spatial topology comprises: {', '.join(f'{k}: {v}' for k, v in sorted(cluster_dist.items())) or '0 clusters'}."
        )

        limitations = (
            f"Physical evidence coverage ({coverage_str}) reflects unique 1D interval unions across scoped buffers. "
            f"Candidate aggregate volume ({v_bytes} verified bytes) reflects multiple hypothesis evaluations and must NOT be interpreted as physical disk size."
        )
        if facts.candidate_cap_enforced:
            limitations += (
                f" Candidate cap was enforced: {facts.candidates_omitted} candidate(s) were omitted due to budget limits, representing a bounded evidence subset."
            )

        recommended_next_steps = (
            "Prioritize examination of CRITICAL and HIGH priority clusters, review coextensive and overlapping boundary conflicts, and export mathematically verified evidence digests for judicial reporting."
        )

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

    def _call_gemini(
        self, prompt: str, default_summary: str
    ) -> ProviderInterpretationOutput:
        # Precedence: OFFLINE MODE > API KEY
        if os.getenv("RECOVERIX_OFFLINE", "0").lower() in ("1", "true", "yes"):
            raise RuntimeError("Offline mode enabled (RECOVERIX_OFFLINE=1): external AI provider is blocked")

        if not self.api_key:
            raise RuntimeError("Gemini API key is not configured")

        import httpx

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

            summary = parsed.get("summary") or default_summary
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

    def interpret_artifact(
        self, context: ArtifactInterpretationContext
    ) -> ProviderInterpretationOutput:
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

        return self._call_gemini(
            prompt,
            default_summary=f"Grounded explanation for {context.facts.category} artifact.",
        )

    def interpret_cluster(
        self, context: ClusterInterpretationContext
    ) -> ProviderInterpretationOutput:
        facts = context.facts
        facts_dict = facts.model_dump()
        u_bytes_str = f"{facts.unique_physical_bytes} bytes" if facts.unique_physical_bytes is not None else "unbounded"

        prompt = (
            "You are the Recoverix AI Evidence Analyst, a digital forensics investigator assistant.\n"
            "Interpret ONLY the following deterministic spatial cluster facts established by the reconstruction and graph engines.\n"
            "CRITICAL FORENSIC RULES:\n"
            "1. You MUST NOT invent bytes, modify bytes, or override V/R/M.\n"
            "2. You MUST NOT refer to candidate aggregate verified bytes as 'total bytes recovered' or 'physical disk recovery'.\n"
            f"   The physical evidence footprint is {u_bytes_str}, whereas candidate evaluations total {facts.candidate_aggregate_verified_bytes} verified bytes across competing or nested format hypotheses.\n"
            "3. In COEXTENSIVE clusters, you MUST NOT declare a single winning format or claim an alternative hypothesis is false. Compare competing format evidence neutrally.\n"
            "4. You MUST NOT make legal conclusions, determine criminal intent, or identify suspects.\n"
            "5. You MUST acknowledge all corrupted, missing, or reconstructed regions explicitly.\n\n"
            f"DETERMINISTIC CLUSTER FACTS:\n{json.dumps(facts_dict, indent=2)}\n\n"
            "Return a JSON object with EXACTLY these string keys:\n"
            '- "summary": Concise executive overview.\n'
            '- "assessment": Factual forensic analysis of surviving evidence vs conflicting hypotheses.\n'
            '- "structural_context": Spatial relationships, format markers, container hierarchy, or boundary conflicts.\n'
            '- "limitations": Explicit declaration of physical footprint vs candidate aggregate volumes and refusal to declare speculative winners.\n'
            '- "recommended_next_steps": Concrete recommended next investigative step for examiners.\n'
            '- "details": List of 3 to 5 concise analytical bullet statements.\n'
        )

        return self._call_gemini(
            prompt,
            default_summary=f"Grounded cluster synthesis for {facts.relationship_classification} component.",
        )

    def interpret_case(
        self, context: CaseInterpretationContext
    ) -> ProviderInterpretationOutput:
        facts = context.facts
        facts_dict = facts.model_dump()
        cov_str = f"{facts.case_physical_coverage_bytes} bytes" if facts.case_physical_coverage_bytes is not None else "partial/unbounded"

        prompt = (
            "You are the Recoverix AI Evidence Analyst, a digital forensics investigator assistant.\n"
            "Interpret ONLY the following deterministic case facts and provide an executive forensic briefing.\n"
            "CRITICAL FORENSIC RULES:\n"
            "1. You MUST NOT invent bytes, modify bytes, or override V/R/M.\n"
            "2. You MUST NOT call candidate aggregate volume 'total recovered bytes'. Physical evidence coverage across scoped buffers is {cov_str}.\n"
            "3. If candidate_cap_enforced is True, you MUST explicitly disclose that candidates were omitted due to budget limits.\n"
            "4. You MUST NOT make legal conclusions, determine criminal intent, or identify suspects.\n\n"
            f"DETERMINISTIC CASE FACTS:\n{json.dumps(facts_dict, indent=2)}\n\n"
            "Return a JSON object with EXACTLY these string keys:\n"
            '- "summary": Concise executive overview of the case recovery findings.\n'
            '- "assessment": Holistic assessment of overall recovery health and evidence integrity.\n'
            '- "structural_context": Graph topology, cluster distributions, and evidence buffer breakdown.\n'
            '- "limitations": Explicit distinction between physical coverage and candidate volumes, including cap disclosures.\n'
            '- "recommended_next_steps": Strategic next investigative steps for forensic examiners.\n'
            '- "details": List of 3 to 5 concise analytical bullet statements.\n'
        )

        return self._call_gemini(
            prompt,
            default_summary=f"Executive forensic briefing for Case '{facts.case_id}'.",
        )
