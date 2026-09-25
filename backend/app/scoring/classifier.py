"""
classifier.py — Artifact Classification (Stage 9)
"""

def classify_artifact(format: str, content_preview: str | None = None) -> str:
    """
    Deterministically classify artifacts into: DOCUMENT, DATABASE_LOG, PHOTO_MEDIA, SYSTEM_TRACE, BINARY_ARCHIVE.
    """
    if format in ["png", "jpg", "jpeg", "gif"]:
        return "PHOTO_MEDIA"
    if format in ["exe", "dll", "zip", "bin"]:
        return "BINARY_ARCHIVE"
    if format in ["csv", "db", "sql", "sqlite"]:
        return "DATABASE_LOG"
    
    text = (content_preview or "").lower()
    if "auth_success" in text or "sudo" in text or "ip address" in text or "login" in text:
        return "SYSTEM_TRACE"
        
    return "DOCUMENT"
