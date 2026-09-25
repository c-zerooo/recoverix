from __future__ import annotations
import traceback

def ensure_case_001_seeded():
    """Idempotent helper to seed case_001 if it does not exist."""
    try:
        from backend.app.store import store
        if store.get_case("case_001"):
            return
            
        import datetime
        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        with store._lock:
            if "case_001" in store._cases:
                return
            store._cases["case_001"] = {
                "case_id": "case_001",
                "name": "Operation Phantom",
                "description": "Investigation into unauthorized access.",
                "created_at": created_at,
                "evidence": None,
                "artifact_count": 0,
            }
            store._case_artifacts["case_001"] = []
            
        content = (
            # a) Contiguous CRITICAL SYSTEM_TRACE TXT
            b"[SYNTHETIC_ARTIFACT_START]\n"
            b"filename: auth_trace.txt\n"
            b"2026-09-21T08:15:02Z sudo_exec user=root ip address=192.168.1.100\n"
            b"2026-09-21T08:15:05Z sudo_exec user=root ip address=192.168.1.100\n"
            b"[SYNTHETIC_ARTIFACT_END]\n"

            # b) Contiguous HIGH DATABASE_LOG CSV
            b"[SYNTHETIC_ARTIFACT_START]\n"
            b"filename: ledger.csv\n"
            b"txn_id,date,amount,account\n"
            b"1,2026-09-21,500.00,ACC1\n"
            b"[SYNTHETIC_ARTIFACT_END]\n"
            
            # c) Bifragment gap CSV (We will override metadata post-analysis)
            b"[SYNTHETIC_ARTIFACT_START]\n"
            b"filename: fragmented_contacts.csv\n"
            b"id,name,email\n"
            b"1,John,john@example.com\n"
            b"[SYNTHETIC_ARTIFACT_END]\n"

            # d) Corrupted PNG (Causes UTF-8 decode failure -> CORRUPTED)
            b"[SYNTHETIC_ARTIFACT_START]\n"
            b"filename: corrupted.png\n"
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRcorrupted_noise\n"
            b"[SYNTHETIC_ARTIFACT_END]\n"
        )
        store.add_evidence("case_001", "phantom_disk.img", content)
        
        from backend.app.api.analysis import analyze_case
        analyze_case("case_001")
        
        from backend.app.api.artifacts import _enrich_artifact
        for art in store.get_case_artifacts("case_001") or []:
            _enrich_artifact(art)
    except Exception as e:
        print(f"Error seeding case_001: {e}")
        traceback.print_exc()
