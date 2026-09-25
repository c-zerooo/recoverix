"""
priority.py — Artifact Prioritization (Stage 10)
"""

def determine_priority(category: str, content_preview: str | None = None, status: str = "UNRECOVERABLE") -> str:
    """
    Deterministically assign: CRITICAL, HIGH, MEDIUM, LOW.
    """
    if status == "UNRECOVERABLE":
        return "LOW"

    text = (content_preview or "").lower()
    
    # CRITICAL: credentials, keys, evidence of privileged execution
    if "password" in text or "private key" in text or "sudo_exec" in text:
        return "CRITICAL"
        
    # HIGH: financial amounts, transactions, auth failures, IPs, URLs
    if category == "DATABASE_LOG" and ("amount" in text or "transaction" in text or "balance" in text):
        return "HIGH"
    if category == "SYSTEM_TRACE" and ("auth_failure" in text or "ip address" in text or "url" in text):
        return "HIGH"
    if category == "PHOTO_MEDIA":
        return "HIGH"
        
    if category in ["DOCUMENT", "SYSTEM_TRACE", "DATABASE_LOG"]:
        return "MEDIUM"
        
    return "LOW"
