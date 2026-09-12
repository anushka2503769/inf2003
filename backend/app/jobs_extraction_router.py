import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from pymongo.database import Database

from backend.app.db import get_db
from backend.app.job_skill_extraction import extract_skills_from_job

router = APIRouter(prefix="/api/jobs", tags=["jobs-extraction"])


class ExtractSkillsResult(BaseModel):
    job_id: str
    matched_skill_ids: List[int]


class BatchExtractResponse(BaseModel):
    processed_count: int
    results: List[ExtractSkillsResult]


def _extract_title(raw_jd: str) -> str:
    """Pulls 'title' back out of raw_jd's JSON, for backfilling older documents
    that were inserted before 'title' became a top-level field."""
    try:
        job = json.loads(raw_jd)
        if isinstance(job, dict):
            return job.get("title", "Untitled Role")
    except (json.JSONDecodeError, TypeError):
        pass
    return "Untitled Role"


@router.post("/{job_id}/extract-skills", response_model=ExtractSkillsResult)
def extract_skills_for_job(job_id: str, db: Database = Depends(get_db)) -> ExtractSkillsResult:
    """Re-runs skill extraction on one job_documents entry and saves the result."""
    doc = db["job_documents"].find_one({"job_id": job_id})
    if doc is None:
        raise HTTPException(status_code=404, detail=f"No job document found for job_id={job_id}")

    extracted_data = extract_skills_from_job(doc["raw_jd"])
    title = doc.get("title") or _extract_title(doc["raw_jd"])

    db["job_documents"].update_one(
        {"job_id": job_id},
        {"$set": {"extracted_data": extracted_data, "title": title}},
    )

    matched_ids = [req["skill_id"] for req in extracted_data["requirements"]]
    return ExtractSkillsResult(job_id=job_id, matched_skill_ids=matched_ids)


@router.post("/extract-skills/batch", response_model=BatchExtractResponse)
def extract_skills_for_all_jobs(db: Database = Depends(get_db)) -> BatchExtractResponse:
    """
    Re-runs skill extraction on every job_documents entry currently
    stored, and backfills the top-level 'title' field for any older
    documents that were inserted before search support was added.
    """
    results = []

    for doc in db["job_documents"].find({}):
        extracted_data = extract_skills_from_job(doc["raw_jd"])
        title = doc.get("title") or _extract_title(doc["raw_jd"])

        db["job_documents"].update_one(
            {"_id": doc["_id"]},
            {"$set": {"extracted_data": extracted_data, "title": title}},
        )

        matched_ids = [req["skill_id"] for req in extracted_data["requirements"]]
        results.append(ExtractSkillsResult(job_id=doc["job_id"], matched_skill_ids=matched_ids))

    return BatchExtractResponse(processed_count=len(results), results=results)
