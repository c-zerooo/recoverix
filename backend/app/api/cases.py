"""
cases.py — Cases API router for case creation, retrieval, and evidence ingestion.
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Response, status

from backend.app.models.case import CaseCreate, CaseResponse
from backend.app.store import store, MAX_EVIDENCE_SIZE

router = APIRouter(prefix="/cases", tags=["cases"])


@router.post("", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
def create_case(payload: CaseCreate) -> CaseResponse:
    """Create a new forensic recovery case."""
    if not payload.name or not payload.name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid case name. Case name must be a non-empty string.",
        )

    try:
        case_res = store.create_case(name=payload.name, description=payload.description)
        return case_res
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )


@router.get("/{case_id}", response_model=CaseResponse, status_code=status.HTTP_200_OK)
def get_case(case_id: str) -> CaseResponse:
    """Retrieve details for a specific forensic case."""
    case_res = store.get_case(case_id)
    if case_res is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' not found",
        )
    return case_res


@router.post("/{case_id}/evidence", response_model=CaseResponse, status_code=status.HTTP_200_OK)
async def upload_evidence(
    case_id: str,
    request: Request,
    file: Optional[UploadFile] = File(None),
) -> CaseResponse:
    """Upload evidence payload for a specific forensic case."""
    case_res = store.get_case(case_id)
    if case_res is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' not found",
        )

    content: bytes = b""
    filename: str = "evidence.img"

    if file is not None:
        filename = file.filename or "evidence.img"
        try:
            content = await file.read()
        except Exception:
            content = b""

    if not content:
        # Fallback to reading raw body if form upload wasn't used or was empty
        try:
            raw_body = await request.body()
            if raw_body:
                content = raw_body
        except RuntimeError:
            pass

    if not content or len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Evidence file cannot be empty",
        )

    if len(content) > MAX_EVIDENCE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Evidence file size ({len(content)} bytes) exceeds maximum limit of 5 MiB ({MAX_EVIDENCE_SIZE} bytes)",
        )

    try:
        store.add_evidence(case_id, filename, content)
        updated_case = store.get_case(case_id)
        if updated_case is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
        return updated_case
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' not found",
        )
    except ValueError as err:
        err_msg = str(err)
        if "FILE_TOO_LARGE" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Evidence file exceeds maximum limit of 5 MiB",
            )
        elif "EMPTY_FILE" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Evidence file cannot be empty",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=err_msg,
            )
