"""Skill dictionary lookup and a student's confirmed skill membership.

Three routes from docs/API.md. The user id always comes from the verified
token, never from a body or path, because the backend connects with a role that
bypasses RLS and so is the only thing enforcing ownership.

Membership routes answer 204 with no body for both the changed and the already
in-the-desired-state cases: the student asked for a state, and the state holds.
"""

from typing import Annotated

from fastapi import APIRouter, Path, Query, Request, Response, status

from ..auth import CurrentUser
from ..errors import ApiError
from ..schemas import SkillSearchResponse
from ..sql_skills import (
    MAX_SKILL_ID,
    QUERY_MAX_LENGTH,
    SEARCH_LIMIT_DEFAULT,
    SEARCH_LIMIT_MAX,
    SEARCH_LIMIT_MIN,
    add_confirmed_skill,
    remove_confirmed_skill,
    search_skills,
)

router = APIRouter(prefix="/api", tags=["skills"])

# A path id outside PostgreSQL's integer range is a malformed request rather
# than a row that happens to be missing, so it is rejected before any query.
SkillId = Annotated[int, Path(gt=0, le=MAX_SKILL_ID)]

_NO_PROFILE = "You have not set up your profile yet."


def _reject_unknown_parameters(request: Request, allowed: set[str]) -> None:
    """A typo in a filter name must not be silently ignored.

    Returning results for ?limlt=5 would look like the filter worked. FastAPI
    ignores unknown query parameters by default, so this is explicit.
    """
    unknown = sorted(set(request.query_params) - allowed)
    if unknown:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "validation_failed",
            f"Unknown query parameter: {', '.join(unknown)}.",
            {"field": unknown[0]},
        )


def _profile_missing() -> ApiError:
    # The frontend branches on the code; "resource" distinguishes a missing
    # profile from a missing skill without inventing a new top-level code.
    return ApiError(status.HTTP_404_NOT_FOUND, "not_found", _NO_PROFILE, {"resource": "profile"})


@router.get("/skills", response_model=SkillSearchResponse)
def find_skills(
    request: Request,
    user: CurrentUser,
    q: Annotated[str, Query(max_length=QUERY_MAX_LENGTH)] = "",
    limit: Annotated[int, Query(ge=SEARCH_LIMIT_MIN, le=SEARCH_LIMIT_MAX)] = SEARCH_LIMIT_DEFAULT,
) -> SkillSearchResponse:
    """Search the shared dictionary.

    Authenticated but not personal: a student can search before completing
    onboarding, which is what the first-login screen needs.
    """
    _reject_unknown_parameters(request, {"q", "limit"})
    items, has_more = search_skills(q.strip(), limit)
    return SkillSearchResponse(items=items, has_more=has_more)


@router.put("/me/skills/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def confirm_skill(skill_id: SkillId, user: CurrentUser) -> Response:
    """Ensure the signed-in student has this confirmed skill."""
    outcome = add_confirmed_skill(user.user_id, skill_id)
    if outcome == "no_profile":
        raise _profile_missing()
    if outcome == "no_skill":
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "not_found",
            "That skill is no longer in the dictionary.",
            {"resource": "skill"},
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/me/skills/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_skill(skill_id: SkillId, user: CurrentUser) -> Response:
    """Ensure the signed-in student does not have this confirmed skill.

    An unknown skill id is not an error here: the link is absent either way, so
    the requested state already holds. Only the student's own link is removed;
    the shared dictionary entry is untouched.
    """
    if remove_confirmed_skill(user.user_id, skill_id) == "no_profile":
        raise _profile_missing()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
