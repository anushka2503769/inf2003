"""Request and response models.

Field names match frontend/src/types/api.ts exactly. The name rules here mirror
frontend/src/lib/validation.ts; the browser copy is for immediate feedback and
this copy is the one that is actually enforced.
"""

import re
from datetime import datetime
from typing import Annotated, Any, Literal
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


TrackerStatus = Literal["NOT_INTERESTED", "SAVED", "APPLIED", "INTERVIEW", "REJECTED", "OFFER"]


class JobSummary(BaseModel):
    """The job fields a tracker row carries (docs/API.md section 6)."""

    job_id: str
    title: str
    company_name: str
    location: str | None
    job_type: Literal["FULL_TIME", "PART_TIME", "INTERNSHIP"] | None
    work_arrangement: Literal["ONSITE", "HYBRID", "REMOTE"] | None
    application_url: str
    source: str
    source_posted_at: datetime | None
    is_active: bool


class TrackerItem(BaseModel):
    job: JobSummary
    status: TrackerStatus
    created_at: datetime
    updated_at: datetime


class TrackerPutRequest(BaseModel):
    status: TrackerStatus


class TrackerListResponse(BaseModel):
    items: list[TrackerItem]
    total: int


class TrackerSummaryResponse(BaseModel):
    counts: dict[TrackerStatus, int]
    total: int


# Discover (docs/API.md section 7). JobSummary above is shared with the tracker.
JobType = Literal["FULL_TIME", "PART_TIME", "INTERNSHIP"]
WorkArrangement = Literal["ONSITE", "HYBRID", "REMOTE"]


class SkillRequirement(BaseModel):
    skill_id: int
    name: str
    requirement_type: Literal["REQUIRED", "PREFERRED"]


class JobMatch(BaseModel):
    required_total: int
    required_matched: int
    preferred_total: int
    preferred_matched: int
    # required_matched / required_total in 0..1; None when the job lists no
    # REQUIRED skill, which the frontend labels "no requirements extracted".
    coverage: float | None
    matched_skills: list[SkillRequirement]  # REQUIRED first, then by name
    missing_skills: list[SkillRequirement]  # REQUIRED first, then by name


class DiscoverItem(BaseModel):
    job: JobSummary
    match: JobMatch
    rank: int


class DiscoverResponse(BaseModel):
    items: list[DiscoverItem]
    has_more: bool


# Skill gap (docs/API.md section 8, WP-4).


class SkillGapRole(BaseModel):
    role_category: str
    job_count: int


class SkillGapRolesResponse(BaseModel):
    items: list[SkillGapRole]


class SkillGapRow(BaseModel):
    skill_id: int
    name: str
    # Postings in the sample that mention the skill, counted once per job.
    job_count: int
    # job_count / sample_size, 0..1.
    frequency: float
    # required_count + preferred_count == job_count (REQUIRED wins per job).
    required_count: int
    preferred_count: int
    # Shown as "mentioned in N postings (max X yrs)"; never compared to the user.
    max_minimum_years: int | float | None
    years_mentions: int
    user_has: bool


class SkillGapSummary(BaseModel):
    top_n: int
    user_has_in_top_n: int


class SkillGapResponse(BaseModel):
    role_category: str
    sample_size: int
    skills: list[SkillGapRow]
    summary: SkillGapSummary


from .job_fetch_schemas import FetchJobsResponse  # noqa: E402


class FetchSummary(BaseModel):
    requested: int
    inserted: int
    updated: int
    rejected: int
    errors: list[str]


class FetchJobsWithSummaryResponse(FetchJobsResponse):
    summary: FetchSummary
