"""
store.py — Thread-safe in-memory repository for Recoverix cases and artifacts.
"""

from __future__ import annotations

import uuid
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional

from backend.app.models.case import CaseResponse, EvidenceMetadata
from backend.app.models.artifact import ArtifactResponse
from backend.app.models.recovery_run import RecoveryRun
from backend.app.ingestion import compute_metadata, chunk_evidence, Chunk

MAX_EVIDENCE_SIZE = 5 * 1024 * 1024  # 5 MiB limit


class InMemoryStore:
    """Thread-safe repository holding in-memory cases, evidence bytes, chunks, and artifacts."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cases: Dict[str, dict] = {}
        self._evidence: Dict[str, bytes] = {}
        self._chunks: Dict[str, List[Chunk]] = {}
        self._artifacts: Dict[str, ArtifactResponse] = {}
        self._case_artifacts: Dict[str, List[str]] = {}
        self._recovered_files: Dict[str, dict] = {}
        self._recovered_bytes: Dict[str, bytes] = {}
        self._artifact_bytes: Dict[str, bytes] = {}
        self._recovery_runs: Dict[str, RecoveryRun] = {}
        self._artifact_runs: Dict[str, str] = {}

    def clear(self) -> None:
        """Clear all stored state (for test isolation)."""
        with self._lock:
            self._cases.clear()
            self._evidence.clear()
            self._chunks.clear()
            self._artifacts.clear()
            self._case_artifacts.clear()
            self._recovered_files.clear()
            self._recovered_bytes.clear()
            self._artifact_bytes.clear()
            self._recovery_runs.clear()
            self._artifact_runs.clear()

    def create_case(self, name: str, description: Optional[str] = None) -> CaseResponse:
        """Create and store a new forensic case.

        Raises:
            ValueError: If name is empty or invalid.
        """
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Case name cannot be empty or invalid string")

        case_id = f"case_{uuid.uuid4().hex[:8]}"
        created_at = datetime.now(timezone.utc).isoformat()

        with self._lock:
            case_data = {
                "case_id": case_id,
                "name": name.strip(),
                "description": description.strip() if description else None,
                "created_at": created_at,
                "evidence": None,
                "artifact_count": 0,
            }
            self._cases[case_id] = case_data
            self._case_artifacts[case_id] = []
            return CaseResponse(**case_data)

    def get_case(self, case_id: str) -> Optional[CaseResponse]:
        """Retrieve case response model by case_id."""
        with self._lock:
            case_data = self._cases.get(case_id)
            if case_data is None:
                return None

            # Recalculate artifact_count from registered artifacts
            case_copy = dict(case_data)
            case_copy["artifact_count"] = len(self._case_artifacts.get(case_id, []))
            return CaseResponse(**case_copy)

    def list_cases(self) -> List[CaseResponse]:
        """List all stored cases."""
        with self._lock:
            res: List[CaseResponse] = []
            for cid, cdata in self._cases.items():
                ccopy = dict(cdata)
                ccopy["artifact_count"] = len(self._case_artifacts.get(cid, []))
                res.append(CaseResponse(**ccopy))
            return res

    def add_evidence(self, case_id: str, filename: str, content: bytes) -> EvidenceMetadata:
        """Add uploaded evidence bytes to a case using Task 2 ingestion module.

        Reuses Task 2 compute_metadata for SHA-256 and size computation, and chunk_evidence for chunking.

        Raises:
            KeyError: If case_id does not exist.
            ValueError: If file size is 0 (empty) or exceeds MAX_EVIDENCE_SIZE.
        """
        with self._lock:
            if case_id not in self._cases:
                raise KeyError(f"Case '{case_id}' not found")

            if not content or len(content) == 0:
                raise ValueError("EMPTY_FILE")

            if len(content) > MAX_EVIDENCE_SIZE:
                raise ValueError("FILE_TOO_LARGE")

            # Delegate metadata computation (SHA-256) and chunking to Task 2 Ingestion
            ingestion_meta = compute_metadata(content, filename=filename or "evidence.img")
            chunks = chunk_evidence(content)

            meta = EvidenceMetadata(
                filename=ingestion_meta.filename,
                file_size=ingestion_meta.size_bytes,
                uploaded_at=datetime.now(timezone.utc).isoformat(),
                sha256=ingestion_meta.sha256,
            )

            self._cases[case_id]["evidence"] = meta
            self._evidence[case_id] = bytes(content)
            self._chunks[case_id] = chunks
            return meta

    def get_evidence_bytes(self, case_id: str) -> Optional[bytes]:
        """Get uploaded evidence bytes for a case."""
        with self._lock:
            return self._evidence.get(case_id)

    def get_evidence_chunks(self, case_id: str) -> Optional[List[Chunk]]:
        """Get uploaded evidence chunks for a case (Task 2 chunking)."""
        with self._lock:
            return self._chunks.get(case_id)

    def add_artifact(self, artifact: ArtifactResponse) -> ArtifactResponse:
        """Store a recovered artifact under a case.

        Raises:
            KeyError: If case_id is not registered.
        """
        with self._lock:
            if artifact.case_id not in self._cases:
                raise KeyError(f"Case '{artifact.case_id}' not found")

            self._artifacts[artifact.artifact_id] = artifact
            if artifact.artifact_id not in self._case_artifacts[artifact.case_id]:
                self._case_artifacts[artifact.case_id].append(artifact.artifact_id)

            self._cases[artifact.case_id]["artifact_count"] = len(self._case_artifacts[artifact.case_id])
            return artifact

    def get_artifact(self, artifact_id: str) -> Optional[ArtifactResponse]:
        """Get an artifact by artifact_id."""
        with self._lock:
            return self._artifacts.get(artifact_id)

    def get_case_artifacts(self, case_id: str) -> Optional[List[ArtifactResponse]]:
        """Get all artifacts for a given case_id. Returns None if case does not exist."""
        with self._lock:
            if case_id not in self._cases:
                return None
            art_ids = self._case_artifacts.get(case_id, [])
            return [self._artifacts[aid] for aid in art_ids if aid in self._artifacts]

    def store_recovered_file(self, file_id: str, metadata: dict, content: bytes) -> dict:
        """Store single recovered file metadata and raw bytes."""
        with self._lock:
            self._recovered_files[file_id] = metadata
            self._recovered_bytes[file_id] = content
            return metadata

    def get_recovered_file_metadata(self, file_id: str) -> Optional[dict]:
        """Get single recovered file metadata by file_id."""
        with self._lock:
            return self._recovered_files.get(file_id)

    def get_recovered_file_bytes(self, file_id: str) -> Optional[bytes]:
        """Get raw bytes of a single recovered file by file_id."""
        with self._lock:
            return self._recovered_bytes.get(file_id)

    def store_artifact_bytes(self, artifact_id: str, content: bytes) -> None:
        """Store raw bytes of a recovered case artifact."""
        with self._lock:
            self._artifact_bytes[artifact_id] = content

    def get_artifact_bytes(self, artifact_id: str) -> Optional[bytes]:
        """Get raw bytes of a recovered case artifact by artifact_id."""
        with self._lock:
            return self._artifact_bytes.get(artifact_id)

    def add_recovery_run(self, run: RecoveryRun) -> RecoveryRun:
        """Store a RecoveryRun model in memory."""
        with self._lock:
            self._recovery_runs[run.run_id] = run
            if run.artifact_id:
                self._artifact_runs[run.artifact_id] = run.run_id
            return run

    def get_recovery_run(self, run_id: str) -> Optional[RecoveryRun]:
        """Retrieve RecoveryRun by run_id."""
        with self._lock:
            return self._recovery_runs.get(run_id)

    def list_recovery_runs(self) -> List[RecoveryRun]:
        """List all stored RecoveryRun models."""
        with self._lock:
            return list(self._recovery_runs.values())

    def get_recovery_run_by_artifact(self, artifact_id: str) -> Optional[RecoveryRun]:
        """Retrieve RecoveryRun associated with an artifact_id."""
        with self._lock:
            run_id = self._artifact_runs.get(artifact_id)
            if run_id:
                return self._recovery_runs.get(run_id)
            return None


# Global store instance
store = InMemoryStore()
