"""Request and response models.

Field names match frontend/src/types/api.ts exactly. The name rules here mirror
frontend/src/lib/validation.ts; the browser copy is for immediate feedback and
this copy is the one that is actually enforced.
"""

import re
from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

FULL_NAME_MAX_LENGTH = 80

_WHITESPACE = re.compile(r"\s+")
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


def normalise_full_name(value: str) -> str:
    """Collapses internal whitespace and trims, so stored names are consistent."""
    return _WHITESPACE.sub(" ", value).strip()


def _validate_full_name(value: str) -> str:
    name = normalise_full_name(value)
    if not name:
        raise ValueError("Enter the name you want on your profile.")
    if len(name) > FULL_NAME_MAX_LENGTH:
        raise ValueError(f"Use {FULL_NAME_MAX_LENGTH} characters or fewer.")
    if _CONTROL_CHARACTERS.search(name):
        raise ValueError("Remove any special control characters.")
    return name


FullName = Annotated[str, Field(max_length=FULL_NAME_MAX_LENGTH * 4)]


class Profile(BaseModel):
    """A row in the SQL `users` table."""

    user_id: UUID
    full_name: str
    created_at: datetime
    updated_at: datetime


class CreateProfileRequest(BaseModel):
    full_name: FullName

    @field_validator("full_name")
    @classmethod
    def _check(cls, value: str) -> str:
        return _validate_full_name(value)


class UpdateProfileRequest(BaseModel):
    full_name: FullName | None = None

    @field_validator("full_name")
    @classmethod
    def _check(cls, value: str | None) -> str | None:
        return None if value is None else _validate_full_name(value)


class MeResponse(BaseModel):
    profile: Profile
    onboarding_complete: bool
