"""Authenticated search over ready job documents."""

import re
from typing import List

from fastapi import APIRouter, Query
from pydantic import BaseModel
from pymongo.database import Database

from .auth import CurrentUser
from .dependencies import AuthenticatedJobDatabase
from .sql_access import get_active_job_ids

router = APIRouter(prefix="/api/jobs", tags=["jobs-search"])


class JobSearchResult(BaseModel):
    job_id: str
    title: str
    role_category: str
    industry: str
    skill_ids: List[int]


class JobSearchResponse(BaseModel):
    query: str
    result_count: int
    results: List[JobSearchResult]


def ensure_title_indexes(db: Database) -> None:
    db["job_documents"].create_index(
        [("extracted_data.provider.title", "text")], name="provider_title_text_index"
    )
    db["job_documents"].create_index(
        [("extracted_data.provider.title", 1)], name="provider_title_regex_index"
    )


@router.get("/search", response_model=JobSearchResponse)
def search_jobs_by_title(
    user: CurrentUser,
    db: AuthenticatedJobDatabase,
    title: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
) -> JobSearchResponse:
    # A document is visible only when its SQL parent is active and its explicit
    # Mongo readiness marker confirms the cross-store write completed.
    ready_filter = {
        "job_id": {"$in": sorted(get_active_job_ids())},
        "extracted_data.provider.ready": "true",
    }
    try:
        docs = list(
            db["job_documents"]
            .find(
                {"$and": [ready_filter, {"$text": {"$search": title}}]},
                {"score": {"$meta": "textScore"}},
            )
            .sort([("score", {"$meta": "textScore"})])
            .limit(limit)
        )
    except Exception:
        docs = []
    if not docs:
        docs = list(
            db["job_documents"]
            .find(
                {
                    "$and": [
                        ready_filter,
                        {
                            "extracted_data.provider.title": {
                                "$regex": re.escape(title),
                                "$options": "i",
                            }
                        },
                    ]
                }
            )
            .limit(limit)
        )

    results = []
    for doc in docs:
        extracted = doc.get("extracted_data") or {}
        provider = extracted.get("provider") or {}
        requirements = extracted.get("requirements") or []
        results.append(
            JobSearchResult(
                job_id=str(doc.get("job_id", "")),
                title=str(provider.get("title") or "Untitled Role"),
                role_category=str(extracted.get("role_category", "Unclassified")),
                industry=str(extracted.get("industry", "Unclassified")),
                skill_ids=[
                    int(req["skill_id"]) for req in requirements if req.get("skill_id") is not None
                ],
            )
        )
    return JobSearchResponse(query=title, result_count=len(results), results=results)
