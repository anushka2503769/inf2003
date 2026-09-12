"""Profile routes.

Three operations on the signed-in student's own row. The user id always comes
from the verified token and never from the request body or a path parameter, so
one student cannot read or edit another student's profile.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from ..auth import CurrentUser
from ..errors import ApiError
from ..schemas import CreateProfileRequest, MeResponse, Profile, UpdateProfileRequest
from ..store import ProfileStore, get_profile_store

router = APIRouter(prefix="/api", tags=["profile"])

Store = Annotated[ProfileStore, Depends(get_profile_store)]


def _onboarding_complete(profile: Profile) -> bool:
    """Whether the student may enter the main app.

    Having a confirmed name is the whole of onboarding today. When resume upload
    and skill confirmation are added, extend this rule here: the browser reads
    the flag rather than deciding for itself, so the frontend will not change.
    """
    return bool(profile.full_name)


@router.get(
    "/me",
    response_model=MeResponse,
    responses={404: {"description": "Signed in, but onboarding has not run yet"}},
)
def read_me(user: CurrentUser, store: Store) -> MeResponse:
    profile = store.get(user.user_id)
    if profile is None:
        # A normal state for a first-time student, not a failure. The browser
        # sends them to onboarding when it sees this code.
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "not_found",
            "You have not set up your profile yet.",
        )
    return MeResponse(profile=profile, onboarding_complete=_onboarding_complete(profile))


@router.post("/me", response_model=MeResponse, status_code=status.HTTP_200_OK)
def create_me(payload: CreateProfileRequest, user: CurrentUser, store: Store) -> MeResponse:
    """Finishes onboarding by writing the student's chosen name.

    This is an upsert keyed on the token subject rather than a strict create, so
    a retry after a timeout succeeds instead of failing with a conflict the
    student cannot do anything about.
    """
    profile = store.upsert(user.user_id, payload.full_name)
    return MeResponse(profile=profile, onboarding_complete=_onboarding_complete(profile))


@router.patch("/me", response_model=Profile)
def update_me(payload: UpdateProfileRequest, user: CurrentUser, store: Store) -> Profile:
    """Partial update. Currently only the display name is editable."""
    if payload.full_name is None:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "validation_failed",
            "Send at least one field to change.",
        )

    profile = store.update_name(user.user_id, payload.full_name)
    if profile is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "not_found",
            "You have not set up your profile yet.",
        )
    return profile
