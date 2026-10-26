"""Administrator re-extraction with SQL link synchronization."""

import json
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


def _extraction_input(doc: dict) -> str:
    """
    Rebuild what import extracted from. Provider jobs store their JSON as raw_jd,
    but a LinkedIn file import stores only the plain description, so the stored
    title is added back; without it the role is classified from the description alone.
    """
    raw_jd = doc["raw_jd"]
    try:
        if isinstance(json.loads(raw_jd), dict):
            return raw_jd
    except (json.JSONDecodeError, TypeError):
        pass
    title = ((doc.get("extracted_data") or {}).get("provider") or {}).get("title")
    if not title:
        return raw_jd
    return json.dumps({"title": title, "description": raw_jd}, ensure_ascii=False)


def _keep_imported_context(extracted_data: dict, previous: dict) -> None:
    """
    Keep what only import could know: a known industry (LinkedIn supplies its own,
    which the classifier cannot reproduce) and responsibilities parsed from the
    provider's HTML, which is not stored.
    """
    if previous.get("industry") not in (None, "", "Unclassified"):
        extracted_data["industry"] = previous["industry"]
    if not extracted_data.get("responsibilities") and previous.get("responsibilities"):
        extracted_data["responsibilities"] = previous["responsibilities"]


def _extract_one(db: Database, doc: dict) -> ExtractSkillsResult:
    job_id = str(doc.get("job_id", ""))
    try:
        ensure_sql_job_exists(job_id)
        set_job_active(job_id, False)
        previous = doc.get("extracted_data") or {}
        extracted_data = extract_skills_from_job(_extraction_input(doc), require_database=True)
        _keep_imported_context(extracted_data, previous)
        # The stored provider block came from the full provider record at import.
        provider = dict(previous.get("provider") or extracted_data.get("provider") or {})
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
