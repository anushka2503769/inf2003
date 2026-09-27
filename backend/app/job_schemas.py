from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class JobRequirement(BaseModel):
    skill_id: int
    requirement_type: str  # "REQUIRED" or "PREFERRED"
    minimum_years: Optional[int] = None
    evidence: str = Field(min_length=1)


class JobExtractedData(BaseModel):
    role_category: str
    requirements: List[JobRequirement] = Field(default_factory=list)
    responsibilities: List[str] = Field(default_factory=list)
    industry: str | None = None
    provider: dict[str, str] | None = None


class JobIngestResponse(BaseModel):
    document_id: str
    job_id: str
    extracted_at: datetime
    extracted_data: JobExtractedData
