"""Administrator-controlled provider refresh with SQL/Mongo readiness ordering."""

import json
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Query
from pymongo.errors import PyMongoError, WriteError

from .dependencies import AdminJobDatabase
from .errors import ApiError
from .job_fetch_schemas import FetchedJobSummary, FetchJobsResponse
from .job_skill_extraction import extract_skills_from_job
from .job_sources import SOURCE_REGISTRY, ProviderJobError, fetch_from_sources
from .sql_access import (
    SqlAccessError,
    set_job_active,
    upsert_provider_job,
)

router = APIRouter(prefix="/api/jobs/external", tags=["jobs-external"])


@router.post("/fetch-multi", response_model=FetchJobsResponse)
def fetch_and_store_jobs_multi(
    db: AdminJobDatabase,
    sources: List[str] = Query(
        default=["arbeitnow"], description=f"Known sources: {list(SOURCE_REGISTRY)}"
    ),
    limit_per_source: int = Query(5, ge=1, le=2000),
    total_limit: Optional[int] = Query(None, ge=1, le=5000),
) -> FetchJobsResponse:
    effective_limit = limit_per_source
    if total_limit is not None:
        effective_limit = -(-total_limit // len(sources))
    try:
        all_jobs = fetch_from_sources(sources, limit_per_source=effective_limit)
    except ProviderJobError as exc:
        raise ApiError(422, "validation_failed", str(exc)) from exc
    if total_limit is not None:
        all_jobs = all_jobs[:total_limit]
    if not all_jobs:
        raise ApiError(
            502, "service_unavailable", "No valid jobs were returned by the requested source."
        )

    inserted: list[FetchedJobSummary] = []
    for job in all_jobs:
        raw_jd = json.dumps(job, ensure_ascii=False)
        try:
            extracted_data = extract_skills_from_job(raw_jd, require_database=True)
        except Exception as exc:
            raise ApiError(
                503, "service_unavailable", "Canonical skill extraction is temporarily unavailable."
            ) from exc
        if isinstance(extracted_data.get("provider"), dict):
            extracted_data["provider"]["ready"] = "false"
        job_id = None
        try:
            job_id = str(upsert_provider_job(job, extracted_data))
            extracted_at = datetime.now(timezone.utc)
            document = {
                "job_id": job_id,
                "raw_jd": raw_jd,
                "extracted_data": extracted_data,
                "extracted_at": extracted_at,
            }
            collection = db["job_documents"]
            result = collection.replace_one({"job_id": job_id}, document, upsert=True)
            if result.upserted_id is not None:
                document_id = result.upserted_id
            else:
                current = collection.find_one({"job_id": job_id}, {"_id": 1})
                if current is None:
                    raise RuntimeError("MongoDB did not return the replaced job document.")
                document_id = current["_id"]
            collection.update_one(
                {"job_id": job_id}, {"$set": {"extracted_data.provider.ready": "true"}}
            )
            set_job_active(job_id, True)
        except WriteError as exc:
            _mark_provider_pending(job_id, db)
            raise ApiError(
                422, "validation_failed", "A provider job failed MongoDB schema validation."
            ) from exc
        except (PyMongoError, SqlAccessError, RuntimeError) as exc:
            _mark_provider_pending(job_id, db)
            raise ApiError(
                503, "service_unavailable", "Job refresh could not be completed; retry is safe."
            ) from exc

        inserted.append(
            FetchedJobSummary(
                document_id=str(document_id),
                job_id=job_id,
                title=str(job["title"]),
                company_name=str(job["company"]),
                source_url=str(job["url"]),
            )
        )
    return FetchJobsResponse(fetched_count=len(inserted), jobs=inserted)


def _mark_provider_pending(job_id: str | None, db: object | None = None) -> None:
    """Leave both stores pending so a retry cannot expose a partial refresh."""
    if job_id is None:
        return
    if db is not None:
        try:
            db["job_documents"].update_one(
                {"job_id": job_id},
                {"$set": {"extracted_data.provider.ready": "false"}},
            )
        except PyMongoError:
            pass
    try:
        set_job_active(job_id, False)
    except SqlAccessError:
        # The original failure is more useful to the client; retry can repair readiness.
        pass
