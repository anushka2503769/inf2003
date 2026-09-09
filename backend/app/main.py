from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Jobless Simulator API", version="0.1.0")


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["jobless-simulator-api"] = "jobless-simulator-api"


@app.get("/api/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    """Process liveness only; this does not check database connectivity."""
    return HealthResponse()
