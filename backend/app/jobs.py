import json
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from pymongo.database import Database
from pymongo.errors import WriteError

from backend.app.db import get_db
from backend.app.job_extraction import extract_job_fields
from backend.app.job_schemas import JobExtractedData, JobIngestResponse

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class JobIngestRequest(BaseModel):
    job_id: str = Field(..., description="UUID of the job, matches SQL jobs.job_id")
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


@router.get("", response_model=JobListResponse)
def list_jobs(
    skip: int = Query(0, ge=0, description="Number of documents to skip"),
    limit: int = Query(20, ge=1, le=100, description="Max documents to return"),
    role_category: Optional[str] = Query(None, description="Filter by exact role_category"),
    industry: Optional[str] = Query(None, description="Filter by exact industry"),
    db: Database = Depends(get_db),
) -> JobListResponse:
    """
    Lists stored job_documents, newest first, with pagination and
    optional filters. Example:
        GET /api/jobs?skip=0&limit=20&role_category=Software%20Engineering
    """
    query_filter = {}
    if role_category:
        query_filter["extracted_data.role_category"] = role_category
    if industry:
        query_filter["extracted_data.industry"] = industry

    total_count = db["job_documents"].count_documents(query_filter)

    cursor = (
        db["job_documents"]
        .find(query_filter)
        .sort("extracted_at", -1)
        .skip(skip)
        .limit(limit)
    )

    items = []
    for doc in cursor:
        extracted = doc.get("extracted_data", {})
        items.append(
            JobListItem(
                job_id=doc.get("job_id", ""),
                title=doc.get("title", "Untitled Role"),
                role_category=extracted.get("role_category", "Unclassified"),
                industry=extracted.get("industry", "Unclassified"),
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
def get_job_stats(db: Database = Depends(get_db)) -> JobStatsResponse:
    """
    Summary counts across all stored job_documents: how many per
    role_category, per industry, and per source (arbeitnow/devitjobs_uk/
    ai_dev_jobs/manual). Useful for a milestone-report screenshot.
    """
    total_jobs = db["job_documents"].count_documents({})

    role_pipeline = [{"$group": {"_id": "$extracted_data.role_category", "count": {"$sum": 1}}}]
    by_role_category = {
        (doc["_id"] or "Unclassified"): doc["count"]
        for doc in db["job_documents"].aggregate(role_pipeline)
    }

    industry_pipeline = [{"$group": {"_id": "$extracted_data.industry", "count": {"$sum": 1}}}]
    by_industry = {
        (doc["_id"] or "Unclassified"): doc["count"]
        for doc in db["job_documents"].aggregate(industry_pipeline)
    }

    # 'source' lives inside raw_jd's JSON, not as a top-level field, so
    # this can't be a simple $group - parse it per document instead.
    source_counter: Counter = Counter()
    for doc in db["job_documents"].find({}, {"raw_jd": 1}):
        try:
            job = json.loads(doc.get("raw_jd", "{}"))
            source = job.get("source") if isinstance(job, dict) else None
        except (json.JSONDecodeError, TypeError):
            source = None
        source_counter[source or "manual_ingest"] += 1

    return JobStatsResponse(
        total_jobs=total_jobs,
        by_role_category=by_role_category,
        by_industry=by_industry,
        by_source=dict(source_counter),
    )


@router.post("/ingest", response_model=JobIngestResponse)
def ingest_job(
    payload: JobIngestRequest,
    db: Database = Depends(get_db),
) -> JobIngestResponse:
    """
    Accepts a job_id + raw job description text, and stores it in
    job_documents. Structured classification (role_category/requirements/
    responsibilities) is currently a stub - see job_extraction.py.
    """
    if not payload.raw_jd.strip():
        raise HTTPException(status_code=422, detail="raw_jd cannot be blank.")

    extracted_data = extract_job_fields(payload.raw_jd)
    extracted_at = datetime.now(timezone.utc)

    document = {
        "job_id": payload.job_id,
        "raw_jd": payload.raw_jd,
        "extracted_data": extracted_data,
        "extracted_at": extracted_at,
    }

    try:
        result = db["job_documents"].insert_one(document)
    except WriteError as exc:
        raise HTTPException(status_code=422, detail=f"Document failed validation: {exc}") from exc

    return JobIngestResponse(
        document_id=str(result.inserted_id),
        job_id=payload.job_id,
        extracted_at=extracted_at,
        extracted_data=JobExtractedData(**extracted_data),
    )


@router.get("/{job_id}", response_model=JobIngestResponse)
def get_job(job_id: str, db: Database = Depends(get_db)) -> JobIngestResponse:
    """Fetch a stored job_documents entry by its job_id (SQL UUID reference)."""
    doc = db["job_documents"].find_one({"job_id": job_id})
    if doc is None:
        raise HTTPException(status_code=404, detail=f"No job document found for job_id={job_id}")

    return JobIngestResponse(
        document_id=str(doc["_id"]),
        job_id=doc["job_id"],
        extracted_at=doc["extracted_at"],
        extracted_data=JobExtractedData(**doc["extracted_data"]),
    )


@router.delete("/{job_id}", response_model=DeleteJobResponse)
def delete_job(job_id: str, db: Database = Depends(get_db)) -> DeleteJobResponse:
    """Deletes a job_documents entry by its job_id."""
    result = db["job_documents"].delete_one({"job_id": job_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail=f"No job document found for job_id={job_id}")

    return DeleteJobResponse(job_id=job_id, deleted=True)