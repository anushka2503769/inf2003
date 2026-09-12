from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
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
        # Fires if the document doesn't match the collection's validator
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