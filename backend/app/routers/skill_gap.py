"""Skill-gap routes (docs/API.md section 8).

Both routes use ``AuthenticatedJobDatabase``, the same dependency as the job
read routes: it verifies the token, then holds the job pipeline lock for the
request, so the active job ids read from SQL (pipeline step 1) and the Mongo
documents aggregated against them describe one consistent state.
"""

from typing import Annotated

from fastapi import APIRouter, Query, Request, status

from ..auth import CurrentUser
from ..dependencies import AuthenticatedJobDatabase
from ..errors import ApiError
from ..schemas import SkillGapResponse, SkillGapRolesResponse
from ..skill_gap import (
    LIMIT_DEFAULT,
    LIMIT_MAX,
    LIMIT_MIN,
    ROLE_CATEGORY_MAX_LENGTH,
    build_response,
    list_roles,
    skill_gap_mongo,
)
from ..sql_access import get_active_job_ids
from .skills import _reject_unknown_parameters

router = APIRouter(prefix="/api", tags=["skill-gap"])


@router.get("/skill-gap/roles", response_model=SkillGapRolesResponse)
def get_skill_gap_roles(
    request: Request, user: CurrentUser, db: AuthenticatedJobDatabase
) -> SkillGapRolesResponse:
    """Roles with at least one active, ready posting. Not personal: no profile needed."""
    _reject_unknown_parameters(request, set())
    return SkillGapRolesResponse(items=list_roles(db, get_active_job_ids()))


@router.get("/me/skill-gap", response_model=SkillGapResponse)
def get_my_skill_gap(
    request: Request,
    user: CurrentUser,
    db: AuthenticatedJobDatabase,
    role_category: Annotated[str, Query(max_length=ROLE_CATEGORY_MAX_LENGTH)],
    limit: Annotated[int, Query(ge=LIMIT_MIN, le=LIMIT_MAX)] = LIMIT_DEFAULT,
) -> SkillGapResponse:
    """Skills asked for by the role's active postings, marked with the student's own.

    An unknown or empty role is a valid question with an empty answer (200,
    sample_size 0), not an error.
    """
    _reject_unknown_parameters(request, {"role_category", "limit"})
    result = skill_gap_mongo(db, get_active_job_ids(), role_category, user.user_id)
    if result is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "not_found",
            "You have not set up your profile yet.",
            {"resource": "profile"},
        )
    sample_size, rows = result
    return build_response(role_category, sample_size, rows, limit)
