from datetime import datetime, timezone

from fastapi import APIRouter, File, HTTPException, UploadFile
from pymongo.errors import WriteError

from .auth import CurrentUser
from .dependencies import AuthenticatedDatabase
from .document_access import replace_current_resume
from .resume_extraction import (
    extract_raw_text,
    extract_structured_fields,
    resolve_file_kind,
)
from .schemas import ExtractedData, ResumeUploadResponse
from .skills_repository import SkillsRepositoryError
from .sql_access import SqlAccessError, SqlParentMissing, ensure_sql_user_exists

router = APIRouter(prefix="/api/resumes", tags=["resumes"])

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


@router.post("/upload", response_model=ResumeUploadResponse)
async def upload_resume(
    user: CurrentUser,
    db: AuthenticatedDatabase,
    file: UploadFile = File(...),
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

    try:
        extracted_data = extract_structured_fields(raw_text)
    except SkillsRepositoryError as exc:
        raise HTTPException(
            status_code=503, detail="SQL skills dictionary is unavailable."
        ) from exc
    uploaded_at = datetime.now(timezone.utc)

    user_id = str(user.user_id)
    try:
        ensure_sql_user_exists(user_id)
    except SqlParentMissing as exc:
        raise HTTPException(
            status_code=404, detail="Complete your profile before uploading a resume."
        ) from exc
    except SqlAccessError as exc:
        raise HTTPException(
            status_code=503, detail="SQL profile validation is unavailable."
        ) from exc

    document = {
        "user_id": user_id,
        "file_name": file.filename,
        "raw_text": raw_text,
        "extracted_data": extracted_data,
        "uploaded_at": uploaded_at,
    }

    try:
        stored = replace_current_resume(db, document)
    except WriteError as exc:
        # Fires if the document doesn't match the collection's validator
        raise HTTPException(status_code=422, detail="Resume document failed validation.") from exc

    return ResumeUploadResponse(
        resume_id=str(stored["_id"]),
        user_id=stored["user_id"],
        file_name=stored["file_name"],
        uploaded_at=stored["uploaded_at"],
        extracted_data=ExtractedData(**stored["extracted_data"]),
    )
