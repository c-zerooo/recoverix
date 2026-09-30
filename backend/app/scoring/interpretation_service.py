"""
interpretation_service.py — Canonical Grounded Evidence Interpretation Service.

Milestone 3.5.1: The single canonical interpretation pipeline for Recoverix.
Enforces that deterministic recovery facts are strictly immutable and system-owned,
coordinates provider dispatch, handles safe fallback, and persists interpretations to SQLite.
"""

from __future__ import annotations

import os
import re
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from backend.app.models.interpretation import (
    DeterministicArtifactFacts,
    ArtifactInterpretationContext,
    ProviderInterpretationOutput,
    GroundedArtifactInterpretation,
    AuthoritativeRecoveryStatus,
)
from backend.app.scoring.providers import (
    InterpretationProvider,
    DeterministicRuleProvider,
    GeminiInterpretationProvider,
)
from backend.app.scoring.priority import determine_priority
from backend.app.scoring.classifier import classify_artifact

logger = logging.getLogger(__name__)

_GLOBAL_SERVICE: Optional[InterpretationService] = None


class InterpretationService:
    """Canonical service for grounded evidence interpretation."""

    def __init__(
        self,
        primary_provider: Optional[InterpretationProvider] = None,
        fallback_provider: Optional[InterpretationProvider] = None,
        store: Any = None,
    ):
        self._fallback_provider = fallback_provider or DeterministicRuleProvider()
        self._primary_provider = primary_provider or self._resolve_default_primary()
        self._store = store

    def _resolve_default_primary(self) -> InterpretationProvider:
        """Resolve default primary provider based on offline mode and API key."""
        # Precedence: OFFLINE MODE > API KEY
        offline = os.getenv("RECOVERIX_OFFLINE", "0").lower() in ("1", "true", "yes")
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not offline and api_key:
            return GeminiInterpretationProvider(api_key=api_key)
        return self._fallback_provider

    @staticmethod
    def sanitize_preview(raw_preview: Optional[str]) -> Optional[str]:
        """Sanitize and truncate content preview.

        Security boundary disclosure:
        - Bounded to maximum 200 characters.
        - Binary noise and ASCII control characters are stripped.
        - Obvious token and high-entropy secret patterns are redacted.
        - Sanitization reduces obvious leakage patterns but does NOT guarantee detection
          or removal of every sensitive datum. Content preview remains potentially sensitive.
        """
        if not raw_preview:
            return None

        # Truncate strictly to <= 200 chars
        truncated = str(raw_preview)[:200]

        # Strip unprintable binary and ASCII control characters
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\xff]", "", truncated)

        # Redact common token and secret patterns
        cleaned = re.sub(r"Bearer\s+[A-Za-z0-9_\-\.]+", "Bearer [REDACTED]", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"(?:api[_-]?key|password|secret[_-]?key|secret|private[_-]?key)\s*[:=]\s*[^\s]+", "[REDACTED_SECRET]", cleaned, flags=re.IGNORECASE)

        return cleaned.strip()

    @staticmethod
    def extract_artifact_facts(artifact: Any, artifact_id: Optional[str] = None) -> DeterministicArtifactFacts:
        """Extract immutable deterministic facts safely from any artifact/run/dict structure."""
        if isinstance(artifact, dict):
            d = artifact
        elif hasattr(artifact, "model_dump"):
            d = artifact.model_dump()
        elif hasattr(artifact, "__dict__"):
            d = artifact.__dict__
        else:
            d = {}

        art_id = str(
            artifact_id
            or getattr(artifact, "artifact_id", None)
            or getattr(artifact, "file_id", None)
            or d.get("artifact_id")
            or d.get("file_id")
            or "unknown_artifact"
        )
        run_id = getattr(artifact, "run_id", None) or d.get("run_id")
        case_id = getattr(artifact, "case_id", None) or d.get("case_id")

        fmt = str(getattr(artifact, "format", None) or d.get("format") or "unknown").lower()
        filename = str(
            getattr(artifact, "filename", None)
            or getattr(artifact, "original_filename", None)
            or getattr(artifact, "recovered_filename", None)
            or d.get("filename")
            or d.get("original_filename")
            or d.get("recovered_filename")
            or f"evidence.{fmt}"
        )

        preview = str(getattr(artifact, "content_preview", None) or d.get("content_preview") or "")

        # Category
        category = getattr(artifact, "category", None) or d.get("category")
        if not category:
            category = classify_artifact(fmt, preview)
        category = str(category)

        # Authoritative Status
        raw_status = str(getattr(artifact, "status", None) or d.get("status") or "UNRECOVERABLE").upper()
        if raw_status in ("FULLY_RECOVERED", "PARTIALLY_RECOVERED", "CORRUPTED", "UNRECOVERABLE"):
            status: AuthoritativeRecoveryStatus = raw_status  # type: ignore[assignment]
        else:
            status = "UNRECOVERABLE"

        # Byte Accounting ($V, R, M$) and Provenance
        prov = getattr(artifact, "provenance", None) or d.get("provenance")
        v_bytes = 0
        r_bytes = 0
        m_bytes = 0
        method = "NONE"
        validation_status = "PASSED" if status != "UNRECOVERABLE" else "FAILED"
        ev_file_id = None
        ev_start = None
        ev_end = None

        if prov is not None:
            if isinstance(prov, dict):
                v_bytes = prov.get("verified_bytes") or 0
                r_bytes = prov.get("reconstructed_bytes") or 0
                m_bytes = prov.get("missing_bytes") or 0
                method = prov.get("reconstruction_method") or "NONE"
                validation_status = (
                    prov.get("validation_status")
                    or ("PASSED" if status != "UNRECOVERABLE" else "FAILED")
                )
                ev_file_id = prov.get("evidence_file_id")
                ev_start = prov.get("evidence_start")
                ev_end = prov.get("evidence_end")
            else:
                v_bytes = getattr(prov, "verified_bytes", 0) or 0
                r_bytes = getattr(prov, "reconstructed_bytes", 0) or 0
                m_bytes = getattr(prov, "missing_bytes", 0) or 0
                method = getattr(prov, "reconstruction_method", "NONE") or "NONE"
                validation_status = (
                    getattr(prov, "validation_status", None)
                    or ("PASSED" if status != "UNRECOVERABLE" else "FAILED")
                )
                ev_file_id = getattr(prov, "evidence_file_id", None)
                ev_start = getattr(prov, "evidence_start", None)
                ev_end = getattr(prov, "evidence_end", None)

        if not v_bytes:
            v_bytes = (
                getattr(artifact, "verified_bytes", None)
                or getattr(artifact, "total_verified_bytes", None)
                or d.get("verified_bytes")
                or d.get("total_verified_bytes")
                or 0
            )
        if not r_bytes:
            r_bytes = (
                getattr(artifact, "reconstructed_bytes", None)
                or getattr(artifact, "total_reconstructed_bytes", None)
                or d.get("reconstructed_bytes")
                or d.get("total_reconstructed_bytes")
                or 0
            )
        if not m_bytes:
            m_bytes = (
                getattr(artifact, "missing_bytes", None)
                or getattr(artifact, "total_missing_bytes", None)
                or d.get("missing_bytes")
                or d.get("total_missing_bytes")
                or 0
            )
        if not method or method == "NONE":
            method = (
                getattr(artifact, "reconstruction_method", None)
                or d.get("reconstruction_method")
                or (d.get("reconstruction_steps", [{}])[0].get("method") if d.get("reconstruction_steps") else "NONE")
            )
        if not validation_status:
            validation_status = (
                getattr(artifact, "validation_status", None)
                or d.get("validation_status")
                or ("PASSED" if status != "UNRECOVERABLE" else "FAILED")
            )

        v_bytes = int(v_bytes)
        r_bytes = int(r_bytes)
        m_bytes = int(m_bytes)
        method = str(method)
        validation_status = str(validation_status)

        total_input_bytes = (
            getattr(artifact, "total_input_bytes", None)
            or d.get("total_input_bytes")
            or (v_bytes + r_bytes + m_bytes if (v_bytes + r_bytes + m_bytes) > 0 else None)
        )
        if total_input_bytes is not None:
            total_input_bytes = int(total_input_bytes)

        # Coordinates and metadata
        if not ev_file_id:
            ev_file_id = getattr(artifact, "evidence_file_id", None) or d.get("evidence_file_id")
        if ev_start is None:
            ev_start = getattr(artifact, "evidence_start", None) or d.get("evidence_start")
        if ev_end is None:
            ev_end = getattr(artifact, "evidence_end", None) or d.get("evidence_end")

        # Confidence Score (0.0 to 100.0)
        score: Any = 0
        if hasattr(artifact, "confidence_score") and artifact.confidence_score is not None:
            score = artifact.confidence_score
        elif hasattr(artifact, "confidence") and isinstance(artifact.confidence, dict):
            score = artifact.confidence.get("total", 0)
        elif hasattr(artifact, "confidence") and isinstance(artifact.confidence, (int, float)):
            score = artifact.confidence
        elif "confidence_score" in d and d["confidence_score"] is not None:
            score = d["confidence_score"]
        elif "confidence" in d and isinstance(d["confidence"], dict):
            score = d["confidence"].get("total", 0)
        elif "confidence" in d and isinstance(d["confidence"], (int, float)):
            score = d["confidence"]

        try:
            score_float = float(score)
            if score_float < 0.0:
                score_float = 0.0
            elif score_float > 100.0:
                score_float = 100.0
        except (ValueError, TypeError):
            score_float = 0.0

        # Deterministic Priority
        priority = getattr(artifact, "priority", None) or d.get("priority")
        if not priority or priority == "Unknown":
            priority = determine_priority(category, preview, status)
            if status == "PARTIALLY_RECOVERED" and m_bytes > 0 and priority != "CRITICAL":
                priority = "HIGH"
            elif status == "FULLY_RECOVERED" and priority not in ("CRITICAL", "HIGH"):
                priority = "LOW"
            elif status == "UNRECOVERABLE":
                priority = "LOW"

        priority_str = str(priority).upper()
        if priority_str not in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            priority_str = "LOW"


        damage_regions = getattr(artifact, "damage_regions", None) or d.get("damage_regions") or []
        damage_count = len(damage_regions) if isinstance(damage_regions, list) else 0

        is_ambiguous = bool(getattr(artifact, "is_ambiguous", None) or d.get("is_ambiguous") or False)

        return DeterministicArtifactFacts(
            artifact_id=art_id,
            run_id=run_id,
            case_id=case_id,
            evidence_file_id=ev_file_id,
            filename=filename,
            format=fmt,
            category=category,
            status=status,
            confidence_score=score_float,
            priority=priority_str,  # type: ignore[arg-type]
            verified_bytes=v_bytes,
            reconstructed_bytes=r_bytes,
            missing_bytes=m_bytes,
            total_input_bytes=total_input_bytes,
            reconstruction_method=method,
            validation_status=validation_status,
            damage_region_count=damage_count,
            is_ambiguous=is_ambiguous,
            evidence_start=int(ev_start) if ev_start is not None else None,
            evidence_end=int(ev_end) if ev_end is not None else None,
        )

    def _invoke_with_fallback(
        self, context: ArtifactInterpretationContext
    ) -> Tuple[ProviderInterpretationOutput, str]:
        """Invoke primary provider with silent deterministic fallback on failure."""
        offline = os.getenv("RECOVERIX_OFFLINE", "0").lower() in ("1", "true", "yes")

        if not offline and self._primary_provider is not self._fallback_provider:
            try:
                output = self._primary_provider.interpret_artifact(context)
                return output, "GEMINI_1_5_FLASH"
            except Exception as e:
                logger.warning(
                    f"Primary external AI provider call failed or timed out: {e}. "
                    "Falling back seamlessly to DeterministicRuleProvider."
                )

        output = self._fallback_provider.interpret_artifact(context)
        return output, "DETERMINISTIC_RULES"

    def interpret_artifact(
        self,
        artifact_id: str,
        artifact: Any,
        force_refresh: bool = False,
        include_preview: bool = True,
    ) -> GroundedArtifactInterpretation:
        """Interpret a single artifact with caching, persistence, and safe fallback."""
        # 1. Check existing persistence or cache if refresh is not forced
        if not force_refresh:
            existing_summary = getattr(artifact, "ai_summary", None)
            if existing_summary:
                try:
                    data = (
                        json.loads(existing_summary)
                        if isinstance(existing_summary, str)
                        else existing_summary
                    )
                    if isinstance(data, dict) and "facts" in data and "interpretation" in data:
                        return GroundedArtifactInterpretation.model_validate(data).with_cached(True)
                except Exception as e:
                    logger.warning(
                        f"Persisted ai_summary for artifact '{artifact_id}' was malformed: {e}. "
                        "Regenerating interpretation safely without crashing."
                    )

        # 2. Extract immutable deterministic facts
        facts = self.extract_artifact_facts(artifact, artifact_id=artifact_id)

        # 3. Sanitize preview (strictly bounded to <= 200 chars; never raw bytes)
        raw_preview = getattr(artifact, "content_preview", None)
        if raw_preview is None and isinstance(artifact, dict):
            raw_preview = artifact.get("content_preview")
        preview = self.sanitize_preview(raw_preview) if include_preview else None

        # 4. Build context
        context = ArtifactInterpretationContext(facts=facts, content_preview=preview)

        # 5. Invoke provider with fallback
        output, source = self._invoke_with_fallback(context)

        # 6. Fact binding: system facts strictly bound, discarding any provider overrides
        interpretation = GroundedArtifactInterpretation(
            facts=facts,
            interpretation=output,
            source=source,  # type: ignore[arg-type]
            cached=False,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        # 7. Persist to SQLite if store is available
        if self._store is not None and hasattr(self._store, "update_artifact_ai_summary"):
            try:
                self._store.update_artifact_ai_summary(
                    artifact_id=artifact_id,
                    ai_summary=json.dumps(interpretation.model_dump()),
                )
            except Exception as e:
                logger.warning(f"Failed to persist ai_summary to SQLite for artifact '{artifact_id}': {e}")

        # Update in-memory artifact object if attribute exists
        if hasattr(artifact, "ai_summary"):
            try:
                artifact.ai_summary = json.dumps(interpretation.model_dump())
            except Exception:
                pass

        return interpretation


def get_interpretation_service(store: Any = None) -> InterpretationService:
    """Retrieve or initialize the global InterpretationService singleton."""
    global _GLOBAL_SERVICE
    if _GLOBAL_SERVICE is None:
        from backend.app.store import store as default_store
        _GLOBAL_SERVICE = InterpretationService(store=store or default_store)
    elif store is not None and _GLOBAL_SERVICE._store is None:
        _GLOBAL_SERVICE._store = store
    return _GLOBAL_SERVICE
