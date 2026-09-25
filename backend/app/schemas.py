"""Request and response models.

Field names match frontend/src/types/api.ts exactly. The name rules here mirror
frontend/src/lib/validation.ts; the browser copy is for immediate feedback and
this copy is the one that is actually enforced.
"""

import re
from datetime import datetime
from typing import Annotated, Any
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


class Skill(BaseModel):
    """An entry in the shared SQL skill dictionary."""

    skill_id: int
    name: str


class SkillSearchResponse(BaseModel):
    items: list[Skill]
    has_more: bool


class MeResponse(BaseModel):
    profile: Profile
    # Always an array, empty for a student who has confirmed nothing yet. The
    # skill editor re-reads GET /api/me after each change rather than keeping
    # its own copy, so this is the single source of confirmed membership.
    skills: list[Skill] = []
    onboarding_complete: bool


class ExtractedData(BaseModel):
    skills: list[str] = Field(default_factory=list)
    education: list[dict[str, Any]] = Field(default_factory=list)
    experience: list[dict[str, Any]] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)


class ResumeUploadResponse(BaseModel):
    resume_id: str
    user_id: str
    file_name: str
    uploaded_at: datetime
    extracted_data: ExtractedData
