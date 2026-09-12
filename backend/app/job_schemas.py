from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class JobRequirement(BaseModel):
    skill_id: int
    requirement_type: str  # "REQUIRED" or "PREFERRED"
    minimum_years: Optional[int] = None
    evidence: Optional[str] = None


class JobExtractedData(BaseModel):
    role_category: str
    requirements: List[JobRequirement] = []
    responsibilities: List[str] = []


class JobIngestResponse(BaseModel):
    document_id: str
    job_id: str
    extracted_at: datetime
    extracted_data: JobExtractedData