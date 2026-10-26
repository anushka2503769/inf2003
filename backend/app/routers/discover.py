"""Discover feed: active jobs the student has not reviewed, ranked by skill coverage.

docs/API.md section 7. The user id always comes from the verified token; no
query parameter can name another user. The ranking lives in one SQL statement
in sql_discover.py.

Discover reads jobs and job_skills, which the admin pipeline rewrites, so the
route holds the job pipeline lock for the duration of the query, like the other
job read routes. It does not use get_authenticated_job_db because that also
opens MongoDB, and Discover is SQL-only: it must work with MONGODB_URI unset.
"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from ..auth import CurrentUser
from ..errors import ApiError
from ..schemas import DiscoverResponse, JobType, WorkArrangement
from ..sql_access import SqlAccessError, job_read_lock
from ..sql_discover import (
    LIMIT_DEFAULT,
    LIMIT_MAX,
    OFFSET_MAX,
    TEXT_FILTER_MAX_LENGTH,
    DiscoverFilters,
    DiscoverProfileMissing,
    DiscoverStore,
    get_discover_store,
)

router = APIRouter(prefix="/api", tags=["discover"])

Store = Annotated[DiscoverStore, Depends(get_discover_store)]
TextFilter = Annotated[str | None, Query(max_length=TEXT_FILTER_MAX_LENGTH)]

_ALLOWED_PARAMETERS = {"job_type", "work_arrangement", "location", "q", "limit", "offset"}


def _reject_unknown_parameters(request: Request) -> None:
    """A typo in a filter name must not silently return an unfiltered feed."""
    unknown = sorted(set(request.query_params) - _ALLOWED_PARAMETERS)
    if unknown:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "validation_failed",
            f"Unknown query parameter: {', '.join(unknown)}.",
            {"field": unknown[0]},
        )


def hold_job_read_lock(user: CurrentUser) -> Iterator[None]:
    """Authenticate first, then hold the shared job read lock, without Mongo.

    Mirrors dependencies.get_authenticated_job_db minus get_db(). Busy or
    unavailable maps to the same 503 as the other job read routes.
    """
    try:
        with job_read_lock():
            yield
    except SqlAccessError as exc:
        raise ApiError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "service_unavailable",
            "Job synchronization is temporarily unavailable.",
        ) from exc


def _text(field: str, value: str | None) -> str | None:
    """Trim; an empty filter means no filter. NUL cannot be sent to PostgreSQL."""
    if value is not None and "\x00" in value:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "validation_failed",
            "Remove any special control characters.",
            {"field": field},
        )
    value = (value or "").strip()
    return value or None


@router.get(
    "/discover",
    response_model=DiscoverResponse,
    dependencies=[Depends(hold_job_read_lock)],
)
def discover(
    request: Request,
    user: CurrentUser,
    store: Store,
    job_type: Annotated[JobType | None, Query()] = None,
    work_arrangement: Annotated[WorkArrangement | None, Query()] = None,
    location: TextFilter = None,
    q: TextFilter = None,
    limit: Annotated[int, Query(ge=1, le=LIMIT_MAX)] = LIMIT_DEFAULT,
    offset: Annotated[int, Query(ge=0, le=OFFSET_MAX)] = 0,
) -> DiscoverResponse:
    _reject_unknown_parameters(request)
    filters = DiscoverFilters(
        job_type=job_type,
        work_arrangement=work_arrangement,
        location=_text("location", location),
        q=_text("q", q),
    )
    try:
        return store.feed(user.user_id, filters, limit, offset)
    except DiscoverProfileMissing as exc:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "not_found",
            "You have not set up your profile yet.",
            {"resource": "profile"},
        ) from exc
