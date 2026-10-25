"""Administrator-controlled provider refresh with SQL/Mongo readiness ordering."""

import json
from datetime import datetime, timezone
from typing import List, Optional, Sequence

from fastapi import APIRouter, Query
from pydantic import BaseModel
from pymongo.errors import PyMongoError, WriteError

from .dependencies import AdminJobDatabase
from .errors import ApiError
from .job_fetch_schemas import FetchedJobSummary, FetchJobsResponse
from .job_skill_extraction import extract_skills_from_job
from .job_sources import SOURCE_REGISTRY, ProviderJobError, collect_provider_jobs
from .sql_access import (
    SqlAccessError,
    set_job_active,
    upsert_provider_job_with_status,
)

router = APIRouter(prefix="/api/jobs/external", tags=["jobs-external"])

MAX_REPORTED_ERRORS = 50


class FetchSummary(BaseModel):
    requested: int
    inserted: int
    updated: int
    rejected: int
    errors: List[str]


class FetchJobsWithSummaryResponse(FetchJobsResponse):
    summary: FetchSummary


@router.post("/fetch-multi", response_model=FetchJobsWithSummaryResponse)
def fetch_and_store_jobs_multi(
    db: AdminJobDatabase,
    sources: List[str] = Query(
        default=["arbeitnow"], description=f"Known sources: {list(SOURCE_REGISTRY)}"
    ),
    limit_per_source: int = Query(5, ge=1, le=2000),
    total_limit: Optional[int] = Query(None, ge=1, le=5000),
) -> FetchJobsWithSummaryResponse:
    effective_limit = limit_per_source
    if total_limit is not None:
        effective_limit = -(-total_limit // len(sources))
    try:
        all_jobs, rejected_errors = collect_provider_jobs(sources, limit_per_source=effective_limit)
    except ProviderJobError as exc:
        raise ApiError(422, "validation_failed", str(exc)) from exc
    if total_limit is not None:
        all_jobs = all_jobs[:total_limit]
    if not all_jobs and not rejected_errors:
        raise ApiError(
            502, "service_unavailable", "No valid jobs were returned by the requested source."
        )
    stored, summary = ingest_provider_jobs(db, all_jobs, rejected_errors)
    if not stored:
        every_record_invalid = summary.rejected == len(rejected_errors)
        raise ApiError(
            422 if every_record_invalid else 503,
            "validation_failed" if every_record_invalid else "service_unavailable",
            "No provider job could be stored; see details.summary.errors.",
            {"summary": summary.model_dump()},
        )
    return FetchJobsWithSummaryResponse(fetched_count=len(stored), jobs=stored, summary=summary)


def ingest_provider_jobs(
    db: object, jobs: List[dict], rejected_errors: Sequence[str] = ()
) -> tuple[list[FetchedJobSummary], FetchSummary]:
    """
    Store validated provider jobs one at a time. A record that fails is counted in
    `rejected` with a short message and the rest continue. `rejected_errors` are
    records that were already refused before storage (for example no stable ID).
    Shared by fetch-multi and scripts/ingest_jobs.py.
    """
    stored: list[FetchedJobSummary] = []
    errors: list[str] = list(rejected_errors)
    rejected = len(errors)
    inserted = updated = 0
    for job in jobs:
        try:
            summary, was_inserted = _store_job(db, job)
        except Exception as exc:
            rejected += 1
            errors.append(_describe_failure(job, exc))
            continue
        stored.append(summary)
        if was_inserted:
            inserted += 1
        else:
            updated += 1
    return stored, FetchSummary(
        requested=len(jobs) + len(rejected_errors),
        inserted=inserted,
        updated=updated,
        rejected=rejected,
        errors=errors[:MAX_REPORTED_ERRORS],
    )


def _describe_failure(job: dict, exc: Exception) -> str:
    """One short line per rejected record: never the payload, never a driver message."""
    label = f"{job.get('source', 'unknown')}/{str(job.get('external_job_id', '?'))[:40]}"
    if isinstance(exc, (ApiError, SqlAccessError)):
        reason = str(exc)
    else:
        reason = f"Unexpected {type(exc).__name__} while storing the job."
    return f"{label}: {reason}"[:300]


def _store_job(db: object, job: dict) -> tuple[FetchedJobSummary, bool]:
    store_job = {key: value for key, value in job.items() if key != "raw_jd"}
    extraction_input = json.dumps(store_job, ensure_ascii=False)
    try:
        extracted_data = extract_skills_from_job(extraction_input, require_database=True)
    except Exception as exc:
        raise ApiError(
            503, "service_unavailable", "Canonical skill extraction is temporarily unavailable."
        ) from exc
    if isinstance(extracted_data.get("provider"), dict):
        extracted_data["provider"]["ready"] = "false"
    if job.get("industry"):
        extracted_data["industry"] = str(job["industry"])
    raw_jd = str(job.get("raw_jd") or "").strip() or extraction_input
    job_id = None
    try:
        job_uuid, was_inserted = upsert_provider_job_with_status(job, extracted_data)
        job_id = str(job_uuid)
        extracted_at = datetime.now(timezone.utc)
        document = {
            "job_id": job_id,
            "raw_jd": raw_jd,
            "extracted_data": extracted_data,
            "extracted_at": extracted_at,
        }
        collection = db["job_documents"]  # type: ignore[index]
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
        if isinstance(exc, SqlAccessError) and job_id is None:
            raise  # the upsert itself refused the record (invalid field), not an outage
        raise ApiError(
            503, "service_unavailable", "Job refresh could not be completed; retry is safe."
        ) from exc

    return (
        FetchedJobSummary(
            document_id=str(document_id),
            job_id=job_id,
            title=str(job["title"]),
            company_name=str(job["company"]),
            source_url=str(job["url"]),
        ),
        was_inserted,
    )


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
