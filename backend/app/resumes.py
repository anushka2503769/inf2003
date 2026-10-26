import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile
from pymongo.errors import WriteError

from .auth import CurrentUser
from .dependencies import AuthenticatedDatabase
from .document_access import replace_current_resume
from .errors import ApiError
from .resume_extraction import (
    extract_raw_text,
    extract_structured_fields,
    resolve_file_kind,
)
from .schemas import ExtractedData, ResumeUploadResponse, Skill
from .skills_repository import SkillsRepositoryError, get_all_skills
from .sql_access import SqlAccessError, SqlParentMissing, ensure_sql_user_exists
from .sql_skills import confirmed_skills

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/resumes", tags=["resumes"])

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


def suggest_skills(extracted_names: list[str], user_id: UUID) -> list[Skill]:
    """Map extracted skill names to dictionary entries the caller has not confirmed.

    Matching is case-insensitive on the exact name. Unknown names are dropped,
    duplicates collapse to one entry, and the result is ordered by name.
    Nothing is saved: the client confirms each suggestion with PUT /api/me/skills/{id}.
    """
    try:
        dictionary = get_all_skills()
        confirmed_ids = {skill.skill_id for skill in confirmed_skills(user_id)}
    except SkillsRepositoryError as exc:
        raise ApiError(503, "service_unavailable", "SQL skills dictionary is unavailable.") from exc

    by_name: dict[str, Skill] = {}
    for skill_id, name in sorted(dictionary):
        by_name.setdefault(name.casefold(), Skill(skill_id=skill_id, name=name))

    suggestions: dict[int, Skill] = {}
    for extracted in extracted_names:
        match = by_name.get(str(extracted).strip().casefold())
        if match is not None and match.skill_id not in confirmed_ids:
            suggestions[match.skill_id] = match
    return sorted(suggestions.values(), key=lambda skill: (skill.name.casefold(), skill.skill_id))


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

    user_id = str(user.user_id)
    try:
        ensure_sql_user_exists(user_id)
    except SqlParentMissing as exc:
        raise ApiError(
            404,
            "not_found",
            "Complete your profile before uploading a resume.",
            {"resource": "profile"},
        ) from exc
    except SqlAccessError as exc:
        raise ApiError(
            503, "service_unavailable", "SQL profile validation is unavailable."
        ) from exc

    try:
        raw_text = extract_raw_text(file_bytes, file_kind)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not parse file: {exc}") from exc

    if not raw_text.strip():
        raise HTTPException(status_code=422, detail="No readable text found in file.")

    try:
        extracted_data = extract_structured_fields(raw_text)
    except SkillsRepositoryError as exc:
        raise ApiError(503, "service_unavailable", "SQL skills dictionary is unavailable.") from exc
    uploaded_at = datetime.now(timezone.utc)

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

    # The resume is already stored, so a suggestion lookup failure must not
    # report the upload as failed; the client can fetch GET /api/me/resume later.
    try:
        suggested = suggest_skills(stored["extracted_data"].get("skills", []), user.user_id)
    except (ApiError, SqlAccessError):
        logger.warning("Resume stored but suggested skills were unavailable.")
        suggested = []

    return ResumeUploadResponse(
        resume_id=str(stored["_id"]),
        user_id=stored["user_id"],
        file_name=stored["file_name"],
        uploaded_at=stored["uploaded_at"],
        extracted_data=ExtractedData(**stored["extracted_data"]),
        suggested_skills=suggested,
    )
