"""Tracker routes: a student's decision about each job (docs/API.md section 6).

The user id always comes from the verified token. These routes do not take the
job pipeline lock: they never write to jobs or job_skills.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from ..auth import CurrentUser
from ..errors import ApiError
from ..schemas import (
    TrackerItem,
    TrackerListResponse,
    TrackerPutRequest,
    TrackerStatus,
    TrackerSummaryResponse,
)
from ..sql_tracker import (
    LIMIT_DEFAULT,
    LIMIT_MAX,
    OFFSET_MAX,
    TrackerJobMissing,
    TrackerProfileMissing,
    TrackerStore,
    get_tracker_store,
)

router = APIRouter(prefix="/api", tags=["tracker"])

Store = Annotated[TrackerStore, Depends(get_tracker_store)]


def _reject_unknown_parameters(request: Request, allowed: set[str]) -> None:
    unknown = sorted(set(request.query_params) - allowed)
    if unknown:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "validation_failed",
            f"Unknown query parameter: {', '.join(unknown)}.",
            {"field": unknown[0]},
        )


def _not_found(resource: str, message: str) -> ApiError:
    return ApiError(status.HTTP_404_NOT_FOUND, "not_found", message, {"resource": resource})


def _profile_missing() -> ApiError:
    return _not_found("profile", "You have not set up your profile yet.")


@router.put("/me/jobs/{job_id}", response_model=TrackerItem)
def put_tracker_job(
    job_id: UUID, body: TrackerPutRequest, user: CurrentUser, store: Store
) -> TrackerItem:
    try:
        return store.put(user.user_id, job_id, body.status)
    except TrackerProfileMissing:
        raise _profile_missing() from None
    except TrackerJobMissing:
        raise _not_found("job", "That job is no longer available.") from None


# Registered before the {job_id} routes so "summary" is never read as an id.
@router.get("/me/jobs/summary", response_model=TrackerSummaryResponse)
def tracker_summary(request: Request, user: CurrentUser, store: Store) -> TrackerSummaryResponse:
    _reject_unknown_parameters(request, set())
    counts = store.summary(user.user_id)
    return TrackerSummaryResponse(counts=counts, total=sum(counts.values()))


@router.get("/me/jobs", response_model=TrackerListResponse)
def list_tracker_jobs(
    request: Request,
    user: CurrentUser,
    store: Store,
    status_filter: Annotated[list[TrackerStatus] | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=LIMIT_MAX)] = LIMIT_DEFAULT,
    offset: Annotated[int, Query(ge=0, le=OFFSET_MAX)] = 0,
) -> TrackerListResponse:
    _reject_unknown_parameters(request, {"status", "limit", "offset"})
    items, total = store.list_items(user.user_id, status_filter or None, limit, offset)
    return TrackerListResponse(items=items, total=total)


@router.delete("/me/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tracker_job(job_id: UUID, user: CurrentUser, store: Store) -> Response:
    try:
        store.delete(user.user_id, job_id)
    except TrackerProfileMissing:
        raise _profile_missing() from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
