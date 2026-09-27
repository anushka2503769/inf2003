"""Route dependencies that enforce authentication before opening databases."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from pymongo.database import Database

from .auth import AuthenticatedUser, CurrentUser
from .config import Settings, get_settings
from .db import get_db
from .errors import ApiError
from .sql_access import SqlAccessError, job_pipeline_lock


def get_authenticated_db(user: CurrentUser) -> Database:
    """Open Mongo only after the bearer token has been verified."""
    return get_db()


def require_admin(
    user: CurrentUser, settings: Annotated[Settings, Depends(get_settings)]
) -> AuthenticatedUser:
    """Require an explicit server-side UUID allowlist for global mutations."""
    if user.user_id not in settings.admin_user_ids:
        raise ApiError(
            403, "forbidden", "This operation requires server-authorized administration."
        )
    return user


def get_admin_db(admin: Annotated[AuthenticatedUser, Depends(require_admin)]) -> Database:
    """Open Mongo only after authentication and the admin allowlist check."""
    return get_db()


def get_authenticated_job_db(user: CurrentUser) -> Iterator[Database]:
    """Authenticate first, then hold the cross-store job lock for the route."""
    try:
        with job_pipeline_lock():
            yield get_db()
    except SqlAccessError as exc:
        raise ApiError(
            503, "service_unavailable", "Job synchronization is temporarily unavailable."
        ) from exc


def get_admin_job_db(
    admin: Annotated[AuthenticatedUser, Depends(require_admin)],
) -> Iterator[Database]:
    """Authorize administration before holding the cross-store job lock."""
    try:
        with job_pipeline_lock():
            yield get_db()
    except SqlAccessError as exc:
        raise ApiError(
            503, "service_unavailable", "Job synchronization is temporarily unavailable."
        ) from exc


AuthenticatedDatabase = Annotated[Database, Depends(get_authenticated_db)]
AdminDatabase = Annotated[Database, Depends(get_admin_db)]
AuthenticatedJobDatabase = Annotated[Database, Depends(get_authenticated_job_db)]
AdminJobDatabase = Annotated[Database, Depends(get_admin_job_db)]
