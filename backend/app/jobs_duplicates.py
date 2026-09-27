"""
Detects and removes duplicate job_documents entries.

Duplicate key priority:
1. url (from raw_jd's JSON, if present and non-empty) - most reliable,
   since it points to the exact same posting.
2. (title, company) pair, lowercased - fallback for documents without a
   url (e.g. DevITjobs UK postings, which don't include one), or for
   manually-ingested job descriptions via /api/jobs/ingest where raw_jd
   is plain text, not JSON.

When duplicates are found, the OLDEST document (by extracted_at) in each
group is kept; the rest are considered removable.
"""

import json
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter
from pydantic import BaseModel
from pymongo.database import Database

from .dependencies import AdminJobDatabase
from .errors import ApiError
from .sql_access import get_active_job_ids

router = APIRouter(prefix="/api/jobs", tags=["jobs-duplicates"])


class DuplicateGroup(BaseModel):
    dedup_key: str
    kept_job_id: str
    removed_job_ids: List[str]
    count: int


class DuplicatesPreviewResponse(BaseModel):
    group_count: int
    total_removable: int
    groups: List[DuplicateGroup]


class DuplicatesDeleteResponse(BaseModel):
    group_count: int
    deleted_count: int


def _get_dedup_key(raw_jd: str, title: str) -> Optional[str]:
    """
    Returns a string key to group potential duplicates by, or None if
    even the fallback (title) is missing/blank.
    """
    try:
        job = json.loads(raw_jd)
    except (json.JSONDecodeError, TypeError):
        job = None

    if isinstance(job, dict):
        url = (job.get("url") or "").strip()
        if url:
            return f"url::{url}"

        company = (job.get("company") or job.get("company_name") or "").strip().lower()
        job_title = (job.get("title") or title or "").strip().lower()
        if job_title:
            return f"title_company::{job_title}::{company}"

    # raw_jd wasn't JSON (manual ingest) or had no usable fields - fall
    # back to the top-level title field alone.
    title_clean = (title or "").strip().lower()
    return f"title_only::{title_clean}" if title_clean else None


def _find_duplicate_groups(db: Database) -> List[Tuple[str, List[Dict[str, Any]]]]:
    """
    Returns [(dedup_key, [doc, doc, ...]), ...] for every key that has
    more than one document. Each doc dict has _id, job_id, extracted_at.
    """
    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    cursor = db["job_documents"].find(
        {
            "job_id": {"$in": sorted(get_active_job_ids())},
            "extracted_data.provider.ready": "true",
        },
        {"_id": 1, "job_id": 1, "raw_jd": 1, "title": 1, "extracted_at": 1},
    )
    for doc in cursor:
        key = _get_dedup_key(doc.get("raw_jd", ""), doc.get("title", ""))
        if key is not None:
            buckets[key].append(doc)

    return [(key, docs) for key, docs in buckets.items() if len(docs) > 1]


def _build_groups(db: Database) -> List[DuplicateGroup]:
    groups = []
    for key, docs in _find_duplicate_groups(db):
        # Keep the oldest document (earliest extracted_at); mark the rest removable.
        docs_sorted = sorted(docs, key=lambda d: d.get("extracted_at"))
        kept = docs_sorted[0]
        removed = docs_sorted[1:]

        groups.append(
            DuplicateGroup(
                dedup_key=key,
                kept_job_id=kept["job_id"],
                removed_job_ids=[d["job_id"] for d in removed],
                count=len(docs),
            )
        )
    return groups


@router.get("/duplicates", response_model=DuplicatesPreviewResponse)
def preview_duplicates(db: AdminJobDatabase) -> DuplicatesPreviewResponse:
    """Preview duplicate groups WITHOUT deleting anything."""
    groups = _build_groups(db)
    total_removable = sum(len(g.removed_job_ids) for g in groups)
    return DuplicatesPreviewResponse(
        group_count=len(groups), total_removable=total_removable, groups=groups
    )


@router.delete("/duplicates", response_model=DuplicatesDeleteResponse)
def delete_duplicates(db: AdminJobDatabase) -> DuplicatesDeleteResponse:
    """Deletes duplicate documents, keeping the oldest in each group."""
    raise ApiError(
        409,
        "conflict",
        "Duplicate deletion is disabled until SQL and Mongo cleanup is coordinated.",
    )
