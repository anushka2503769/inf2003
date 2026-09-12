from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from .errors import register_error_handlers
from .routers import profile

app = FastAPI(title="Jobless Simulator API", version="0.1.0")

register_error_handlers(app)
app.include_router(profile.router)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["jobless-simulator-api"] = "jobless-simulator-api"


@app.get("/api/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    """Process liveness only; this does not check database connectivity."""
    return HealthResponse()
