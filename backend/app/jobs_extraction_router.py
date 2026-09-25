"""Administrator re-extraction with SQL link synchronization."""

from typing import List

from fastapi import APIRouter
from pydantic import BaseModel
from pymongo.database import Database
from pymongo.errors import PyMongoError, WriteError

from .dependencies import AdminJobDatabase
from .errors import ApiError
from .job_skill_extraction import extract_skills_from_job
from .sql_access import (
    SqlAccessError,
    SqlParentMissing,
    ensure_sql_job_exists,
    replace_job_skills,
    set_job_active,
)

router = APIRouter(prefix="/api/jobs", tags=["jobs-extraction"])


class ExtractSkillsResult(BaseModel):
    job_id: str
    matched_skill_ids: List[int]


class BatchExtractResponse(BaseModel):
    processed_count: int
    results: List[ExtractSkillsResult]


def _mark_pending(db: Database, document_id: object, job_id: str) -> None:
    """Keep both stores hidden/inactive after a partial re-extraction."""
    try:
        db["job_documents"].update_one(
            {"_id": document_id}, {"$set": {"extracted_data.provider.ready": "false"}}
        )
    except PyMongoError:
        pass
    try:
        set_job_active(job_id, False)
    except SqlAccessError:
        pass


def _extract_one(db: Database, doc: dict) -> ExtractSkillsResult:
    job_id = str(doc.get("job_id", ""))
    try:
        ensure_sql_job_exists(job_id)
        set_job_active(job_id, False)
        extracted_data = extract_skills_from_job(doc["raw_jd"], require_database=True)
        provider = (
            extracted_data.get("provider")
            or (doc.get("extracted_data") or {}).get("provider")
            or {}
        )
        provider["ready"] = "false"
        extracted_data["provider"] = provider
        db["job_documents"].update_one(
            {"_id": doc["_id"]}, {"$set": {"extracted_data": extracted_data}}
        )
        replace_job_skills(job_id, extracted_data["requirements"])
        db["job_documents"].update_one(
            {"_id": doc["_id"]}, {"$set": {"extracted_data.provider.ready": "true"}}
        )
        set_job_active(job_id, True)
    except SqlParentMissing as exc:
        raise ApiError(404, "not_found", "The SQL job does not exist.") from exc
    except WriteError as exc:
        _mark_pending(db, doc.get("_id"), job_id)
        raise ApiError(
            422, "validation_failed", "The extracted document failed schema validation."
        ) from exc
    except (PyMongoError, SqlAccessError, KeyError, RuntimeError) as exc:
        _mark_pending(db, doc.get("_id"), job_id)
        raise ApiError(
            503, "service_unavailable", "Job extraction could not be completed; retry is safe."
        ) from exc
    return ExtractSkillsResult(
        job_id=job_id,
        matched_skill_ids=[int(req["skill_id"]) for req in extracted_data["requirements"]],
    )


@router.post("/{job_id}/extract-skills", response_model=ExtractSkillsResult)
def extract_skills_for_job(job_id: str, db: AdminJobDatabase) -> ExtractSkillsResult:
    doc = db["job_documents"].find_one({"job_id": job_id})
    if doc is None:
        raise ApiError(404, "not_found", "No job document was found.")
    return _extract_one(db, doc)


@router.post("/extract-skills/batch", response_model=BatchExtractResponse)
def extract_skills_for_all_jobs(db: AdminJobDatabase) -> BatchExtractResponse:
    results = [_extract_one(db, doc) for doc in db["job_documents"].find({})]
    return BatchExtractResponse(processed_count=len(results), results=results)
