"""
Fetches jobs from one or more registered sources (see job_sources.py)
and stores each as raw JSON in job_documents - no PDF step, matching
the "just get fetching working" simplified approach.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.database import Database
from pymongo.errors import WriteError

from backend.app.db import get_db
from backend.app.job_fetch_schemas import FetchedJobSummary, FetchJobsResponse
from backend.app.job_skill_extraction import extract_skills_from_job
from backend.app.job_sources import SOURCE_REGISTRY, fetch_from_sources

router = APIRouter(prefix="/api/jobs/external", tags=["jobs-external"])


@router.post("/fetch-multi", response_model=FetchJobsResponse)
def fetch_and_store_jobs_multi(
    sources: List[str] = Query(
        default=["arbeitnow"],
        description=f"Which sources to pull from. Known: {list(SOURCE_REGISTRY.keys())}",
    ),
    limit_per_source: int = Query(5, ge=1, le=2000, description="Max jobs to fetch per source"),
    total_limit: Optional[int] = Query(
        default=None,
        ge=1,
        le=5000,
        description="If set, overrides limit_per_source by splitting this total evenly across the requested sources",
    ),
    db: Database = Depends(get_db),
) -> FetchJobsResponse:
    """
    Example (manual per-source control):
        POST /api/jobs/external/fetch-multi?sources=arbeitnow&sources=devitjobs_uk&limit_per_source=5

    Example (target a total count, auto-split across sources):
        POST /api/jobs/external/fetch-multi?sources=arbeitnow&sources=devitjobs_uk&sources=ai_dev_jobs&total_limit=1000
    """
    effective_limit_per_source = limit_per_source
    if total_limit is not None:
        effective_limit_per_source = -(-total_limit // len(sources))  # ceil division

    all_jobs = fetch_from_sources(sources, limit_per_source=effective_limit_per_source)

    if total_limit is not None:
        all_jobs = all_jobs[:total_limit]  # trim any overshoot from ceil division

    if not all_jobs:
        raise HTTPException(
            status_code=502,
            detail="No jobs returned from any requested source. Check server logs for per-source errors.",
        )

    inserted_summaries = []

    for job in all_jobs:
        job_id = str(uuid.uuid4())
        extracted_at = datetime.now(timezone.utc)
        raw_jd = json.dumps(job, ensure_ascii=False)

        # Classify profession/industry and match skills BEFORE inserting,
        # so job_documents never stores the "Unclassified" stub for jobs
        # fetched through this endpoint.
        extracted_data = extract_skills_from_job(raw_jd)

        document = {
            "job_id": job_id,
            "title": job.get("title", "Untitled Role"),  # top-level for fast/indexed search
            "raw_jd": raw_jd,
            "extracted_data": extracted_data,
            "extracted_at": extracted_at,
        }

        try:
            result = db["job_documents"].insert_one(document)
        except WriteError as exc:
            print(f"[fetch_and_store_jobs_multi] Validator rejected job {job_id}: {exc}")
            continue

        inserted_summaries.append(
            FetchedJobSummary(
                document_id=str(result.inserted_id),
                job_id=job_id,
                title=job.get("title", "Untitled Role"),
                company_name=job.get("company", "Unknown Company"),
                source_url=job.get("url", ""),
            )
        )

    return FetchJobsResponse(fetched_count=len(inserted_summaries), jobs=inserted_summaries)