from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from .errors import register_error_handlers
from .routers import profile

from backend.app import (
    jobs,
    jobs_duplicates,
    jobs_external_multi,
    jobs_extraction_router,
    jobs_search,
    resumes,
    resumes_read
)
#from backend.app import reports

app = FastAPI(title="Jobless Simulator API", version="0.1.0")

register_error_handlers(app)
app.include_router(profile.router)
app.include_router(resumes.router)
app.include_router(resumes_read.router)
app.include_router(jobs_search.router)
app.include_router(jobs_duplicates.router)
app.include_router(jobs.router)
app.include_router(jobs_external_multi.router)
app.include_router(jobs_extraction_router.router)
#app.include_router(reports.router)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["jobless-simulator-api"] = "jobless-simulator-api"


@app.get("/api/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    """Process liveness only; this does not check database connectivity."""
    return HealthResponse()
