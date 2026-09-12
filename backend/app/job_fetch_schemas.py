from typing import List

from pydantic import BaseModel


class FetchedJobSummary(BaseModel):
    document_id: str
    job_id: str
    title: str
    company_name: str
    source_url: str


class FetchJobsResponse(BaseModel):
    fetched_count: int
    jobs: List[FetchedJobSummary]