"""Authenticated job-document reads and administrator-controlled ingestion."""

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from pymongo.database import Database
from pymongo.errors import PyMongoError, WriteError

from .auth import CurrentUser
from .dependencies import AdminJobDatabase, AuthenticatedJobDatabase
from .errors import ApiError
from .job_extraction import extract_job_fields
from .job_schemas import JobExtractedData, JobIngestResponse
from .sql_access import (
    SqlAccessError,
    SqlParentMissing,
    ensure_sql_job_exists,
    get_active_job_ids,
    replace_job_skills,
    set_job_active,
)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class JobIngestRequest(BaseModel):
    job_id: str = Field(..., description="UUID of an existing SQL jobs.job_id")
    raw_jd: str = Field(..., min_length=1, description="Raw job description text")


class JobListItem(BaseModel):
    job_id: str
    title: str
    role_category: str
    industry: str
    extracted_at: datetime


class JobListResponse(BaseModel):
    total_count: int
    returned_count: int
    skip: int
    limit: int
    jobs: List[JobListItem]


class DeleteJobResponse(BaseModel):
    job_id: str
    deleted: bool


class JobStatsResponse(BaseModel):
    total_jobs: int
    by_role_category: Dict[str, int]
    by_industry: Dict[str, int]
    by_source: Dict[str, int]


def _provider(doc: dict[str, Any]) -> dict[str, Any]:
    extracted = doc.get("extracted_data") or {}
    return extracted.get("provider") or {}


def _title(doc: dict[str, Any]) -> str:
    return str(_provider(doc).get("title") or "Untitled Role")


def _mark_pending(db: Database, job_id: str) -> None:
    """Keep an incomplete job hidden in Mongo and inactive in SQL."""
    try:
        db["job_documents"].update_one(
            {"job_id": job_id}, {"$set": {"extracted_data.provider.ready": "false"}}
        )
    except PyMongoError:
        pass
    try:
        set_job_active(job_id, False)
    except SqlAccessError:
        pass


@router.get("", response_model=JobListResponse)
def list_jobs(
    user: CurrentUser,
    db: AuthenticatedJobDatabase,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    role_category: Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
) -> JobListResponse:
    query_filter: dict[str, Any] = {
        "job_id": {"$in": sorted(get_active_job_ids())},
        "extracted_data.provider.ready": "true",
    }
    if role_category:
        query_filter["extracted_data.role_category"] = role_category
    if industry:
        query_filter["extracted_data.industry"] = industry

    collection = db["job_documents"]
    total_count = collection.count_documents(query_filter)
    cursor = collection.find(query_filter).sort("extracted_at", -1).skip(skip).limit(limit)
    items = []
    for doc in cursor:
        extracted = doc.get("extracted_data") or {}
        items.append(
            JobListItem(
                job_id=str(doc.get("job_id", "")),
                title=_title(doc),
                role_category=str(extracted.get("role_category", "Unclassified")),
                industry=str(extracted.get("industry", "Unclassified")),
                extracted_at=doc.get("extracted_at"),
            )
        )
    return JobListResponse(
        total_count=total_count,
        returned_count=len(items),
        skip=skip,
        limit=limit,
        jobs=items,
    )


@router.get("/stats", response_model=JobStatsResponse)
def get_job_stats(user: CurrentUser, db: AuthenticatedJobDatabase) -> JobStatsResponse:
    collection = db["job_documents"]
    ready_filter = {
        "job_id": {"$in": sorted(get_active_job_ids())},
        "extracted_data.provider.ready": "true",
    }
    total_jobs = collection.count_documents(ready_filter)
    role_pipeline = [{"$group": {"_id": "$extracted_data.role_category", "count": {"$sum": 1}}}]
    industry_pipeline = [{"$group": {"_id": "$extracted_data.industry", "count": {"$sum": 1}}}]
    by_role_category = {
        doc.get("_id") or "Unclassified": doc["count"]
        for doc in collection.aggregate([{"$match": ready_filter}, *role_pipeline])
    }
    by_industry = {
        doc.get("_id") or "Unclassified": doc["count"]
        for doc in collection.aggregate([{"$match": ready_filter}, *industry_pipeline])
    }
    source_counter: Counter[str] = Counter()
    for doc in collection.find(ready_filter, {"extracted_data.provider.source": 1}):
        source_counter[_provider(doc).get("source") or "manual_ingest"] += 1
    return JobStatsResponse(
        total_jobs=total_jobs,
        by_role_category=by_role_category,
        by_industry=by_industry,
        by_source=dict(source_counter),
    )


def _store_job_document(db: Database, job_id: str, raw_jd: str) -> JobIngestResponse:
    try:
        extracted_data = extract_job_fields(raw_jd, require_database=True)
    except Exception as exc:
        raise ApiError(
            503, "service_unavailable", "Canonical skill extraction is temporarily unavailable."
        ) from exc
    provider = extracted_data.get("provider") or {}
    provider["ready"] = "false"
    extracted_data["provider"] = provider
    extracted_at = datetime.now(timezone.utc)
    document = {
        "job_id": job_id,
        "raw_jd": raw_jd,
        "extracted_data": extracted_data,
        "extracted_at": extracted_at,
    }
    try:
        set_job_active(job_id, False)
        result = db["job_documents"].replace_one({"job_id": job_id}, document, upsert=True)
        stored_id = result.upserted_id
        if stored_id is None:
            current = db["job_documents"].find_one({"job_id": job_id}, {"_id": 1})
            if current is None:
                raise RuntimeError("MongoDB did not return the replaced job document.")
            stored_id = current["_id"]
        replace_job_skills(job_id, extracted_data.get("requirements", []))
        db["job_documents"].update_one(
            {"job_id": job_id}, {"$set": {"extracted_data.provider.ready": "true"}}
        )
        set_job_active(job_id, True)
    except WriteError as exc:
        _mark_pending(db, job_id)
        raise ApiError(
            422, "validation_failed", "The job document failed schema validation."
        ) from exc
    except (PyMongoError, SqlAccessError, RuntimeError) as exc:
        _mark_pending(db, job_id)
        raise ApiError(
            503, "service_unavailable", "Job storage is temporarily unavailable."
        ) from exc
    return JobIngestResponse(
        document_id=str(stored_id),
        job_id=job_id,
        extracted_at=extracted_at,
        extracted_data=JobExtractedData(**extracted_data),
    )


@router.post("/ingest", response_model=JobIngestResponse)
def ingest_job(payload: JobIngestRequest, db: AdminJobDatabase) -> JobIngestResponse:
    if not payload.raw_jd.strip():
        raise ApiError(422, "validation_failed", "raw_jd cannot be blank.")
    try:
        ensure_sql_job_exists(payload.job_id)
    except SqlParentMissing as exc:
        raise ApiError(404, "not_found", "The SQL job does not exist.") from exc
    except SqlAccessError as exc:
        raise ApiError(
            503, "service_unavailable", "SQL job validation is temporarily unavailable."
        ) from exc
    return _store_job_document(db, payload.job_id, payload.raw_jd)


@router.get("/{job_id}", response_model=JobIngestResponse)
def get_job(job_id: str, user: CurrentUser, db: AuthenticatedJobDatabase) -> JobIngestResponse:
    active_job_ids = get_active_job_ids()
    doc = db["job_documents"].find_one(
        {
            "$and": [
                {"job_id": job_id},
                {"job_id": {"$in": sorted(active_job_ids)}},
                {"extracted_data.provider.ready": "true"},
            ]
        }
    )
    if doc is None:
        raise ApiError(404, "not_found", "No job document was found.")
    return JobIngestResponse(
        document_id=str(doc["_id"]),
        job_id=doc["job_id"],
        extracted_at=doc["extracted_at"],
        extracted_data=JobExtractedData(**doc["extracted_data"]),
    )


@router.delete("/{job_id}", response_model=DeleteJobResponse)
def delete_job(job_id: str, db: AdminJobDatabase) -> DeleteJobResponse:
    raise ApiError(
        409, "conflict", "Job deletion is disabled until SQL and Mongo cleanup is coordinated."
    )
