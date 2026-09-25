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
            # Check again under lock
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
            b"[SYNTHETIC_ARTIFACT_START]\nfilename: ledger.csv\nid,amount,date,status\n1,500.00,2026-09-21,COMPLETED\n2,250.00,2026-09-22,PENDING\n[SYNTHETIC_ARTIFACT_END]\n"
            b"[SYNTHETIC_ARTIFACT_START]\nfilename: evidence_capture.png\n<PNG binary data unrenderable>\n[SYNTHETIC_ARTIFACT_END]\n"
            b"[SYNTHETIC_ARTIFACT_START]\nfilename: auth_trace.txt\n2026-09-21T08:15:02Z AUTH_SUCCESS user=admin\n[SYNTHETIC_ARTIFACT_END]"
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
