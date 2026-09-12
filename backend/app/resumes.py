from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pymongo.database import Database
from pymongo.errors import WriteError

from backend.app.db import get_db
from backend.app.resume_extraction import (
    extract_raw_text,
    extract_structured_fields,
    resolve_file_kind,
)
from backend.app.schemas import ExtractedData, ResumeUploadResponse

router = APIRouter(prefix="/api/resumes", tags=["resumes"])

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


@router.post("/upload", response_model=ResumeUploadResponse)
async def upload_resume(
    user_id: str = Form(..., description="UUID of the user, matches SQL users.user_id"),
    file: UploadFile = File(...),
    db: Database = Depends(get_db),
) -> ResumeUploadResponse:
    """
    Accepts a PDF or DOCX resume, extracts text, and stores it in
    resume_documents. Structured field extraction uses keyword matching
    against the SQL skills table + section-header splitting.
    """
    try:
        file_kind = resolve_file_kind(file.filename, file.content_type)
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 5 MB limit.")

    try:
        raw_text = extract_raw_text(file_bytes, file_kind)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not parse file: {exc}") from exc

    if not raw_text.strip():
        raise HTTPException(status_code=422, detail="No readable text found in file.")

    extracted_data = extract_structured_fields(raw_text)
    uploaded_at = datetime.now(timezone.utc)

    document = {
        "user_id": user_id,
        "file_name": file.filename,
        "raw_text": raw_text,
        "extracted_data": extracted_data,
        "uploaded_at": uploaded_at,
    }

    try:
        result = db["resume_documents"].insert_one(document)
    except WriteError as exc:
        # Fires if the document doesn't match the collection's validator
        raise HTTPException(status_code=422, detail=f"Document failed validation: {exc}") from exc

    return ResumeUploadResponse(
        resume_id=str(result.inserted_id),
        user_id=user_id,
        file_name=file.filename,
        uploaded_at=uploaded_at,
        extracted_data=ExtractedData(**extracted_data),
    )