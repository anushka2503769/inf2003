"""
Search job_documents by title. Uses a MongoDB text index for proper
multi-word relevance-ranked search, with a case-insensitive regex
fallback for simple substring matches (e.g. partial words, which text
indexes don't handle well - "Engineer" won't match a $text search for
"Engin").
"""

from typing import List

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from pymongo.database import Database

from backend.app.db import get_db

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
    """
    Creates the indexes search relies on. Safe to call repeatedly -
    MongoDB no-ops if the index already exists with the same spec.
    Call this once at startup (see main.py) or manually if needed.
    """
    db["job_documents"].create_index([("title", "text")], name="title_text_index")
    db["job_documents"].create_index([("title", 1)], name="title_regex_index")


@router.get("/search", response_model=JobSearchResponse)
def search_jobs_by_title(
    title: str = Query(..., min_length=1, description="Job title keyword(s) to search for"),
    limit: int = Query(20, ge=1, le=100),
    db: Database = Depends(get_db),
) -> JobSearchResponse:
    """
    Example: GET /api/jobs/search?title=python%20developer

    Tries a $text search first (handles multi-word relevance ranking).
    Falls back to a case-insensitive regex "contains" search if $text
    finds nothing - useful for partial words or single short terms that
    $text's word-based matching doesn't handle well.
    """
    text_results = list(
        db["job_documents"]
        .find(
            {"$text": {"$search": title}},
            {"score": {"$meta": "textScore"}},
        )
        .sort([("score", {"$meta": "textScore"})])
        .limit(limit)
    )

    docs = text_results
    if not docs:
        # Fallback: plain case-insensitive substring match
        docs = list(
            db["job_documents"]
            .find({"title": {"$regex": title, "$options": "i"}})
            .limit(limit)
        )

    results = []
    for doc in docs:
        extracted = doc.get("extracted_data", {})
        skill_ids = [req.get("skill_id") for req in extracted.get("requirements", [])]

        results.append(
            JobSearchResult(
                job_id=doc.get("job_id", ""),
                title=doc.get("title", "Untitled Role"),
                role_category=extracted.get("role_category", "Unclassified"),
                industry=extracted.get("industry", "Unclassified"),
                skill_ids=skill_ids,
            )
        )

    return JobSearchResponse(query=title, result_count=len(results), results=results)