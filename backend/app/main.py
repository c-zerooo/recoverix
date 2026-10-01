"""
main.py — FastAPI application entrypoint for Recoverix platform.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.cases import router as cases_router
from backend.app.api.analysis import router as analysis_router
from backend.app.api.artifacts import router as artifacts_router
from backend.app.api.file_recovery import router as file_recovery_router
from backend.app.api.recovery_runs import router as recovery_runs_router
from backend.app.api.evidence_graph import router as evidence_graph_router
from backend.app.api.interpretation import router as interpretation_router
from backend.app.store import store


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    if hasattr(store, "close") and callable(store.close):
        store.close()


app = FastAPI(
    title="Recoverix Forensic Recovery API",
    description="Deterministic forensic artifact recovery, analysis, confidence scoring, and provenance platform.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers matching locked API contract
app.include_router(cases_router, prefix="/api")
app.include_router(analysis_router, prefix="/api")
app.include_router(artifacts_router, prefix="/api")
app.include_router(file_recovery_router, prefix="/api")
app.include_router(recovery_runs_router, prefix="/api")
app.include_router(evidence_graph_router, prefix="/api")
app.include_router(interpretation_router, prefix="/api")


@app.get("/health", tags=["health"])
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "recoverix-api"}

# startup event removed
