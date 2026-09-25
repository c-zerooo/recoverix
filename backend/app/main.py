"""
main.py — FastAPI application entrypoint for Recoverix platform.
"""

from __future__ import annotations

from fastapi import FastAPI
from backend.app.api.cases import router as cases_router
from backend.app.api.analysis import router as analysis_router
from backend.app.api.artifacts import router as artifacts_router

app = FastAPI(
    title="Recoverix Forensic Recovery API",
    description="Deterministic forensic artifact recovery, analysis, confidence scoring, and provenance platform.",
    version="1.0.0",
)

# Include routers matching locked API contract
app.include_router(cases_router, prefix="/api")
app.include_router(analysis_router, prefix="/api")
app.include_router(artifacts_router, prefix="/api")


@app.get("/health", tags=["health"])
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "recoverix-api"}
