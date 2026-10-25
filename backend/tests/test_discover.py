"""Discover route tests with a fake store and a fake job read lock (no database).

The ranking itself is covered against PostgreSQL in test_discover_sql.py. Here
the point is the HTTP contract in docs/API.md section 7: the exact response
shape, validation, the 404 for a missing profile, that the store only ever
sees the verified user id, and that the route holds the job read lock.
"""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
import pytest

from app.auth import AuthenticatedUser, current_user
from app.dependencies import get_authenticated_job_db
from app.main import app
from app.schemas import (
    DiscoverItem,
    DiscoverResponse,
    JobMatch,
    JobSummary,
    SkillRequirement,
)
from app.sql_discover import DiscoverFilters, DiscoverProfileMissing, get_discover_store

ANA = UUID("11111111-1111-4111-8111-111111111111")
BEN = UUID("22222222-2222-4222-8222-222222222222")
JOB_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
JOB_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"

JOB_KEYS = {
    "job_id",
    "title",
    "company_name",
    "location",
    "job_type",
    "work_arrangement",
    "application_url",
    "source",
    "source_posted_at",
    "is_active",
}
MATCH_KEYS = {
    "required_total",
    "required_matched",
    "preferred_total",
    "preferred_matched",
    "coverage",
    "matched_skills",
    "missing_skills",
}


def _job(job_id: str, posted: datetime | None) -> JobSummary:
    return JobSummary(
        job_id=job_id,
        title="Data Intern",
        company_name="Acme",
        location="Singapore",
        job_type="INTERNSHIP",
        work_arrangement=None,
        application_url="https://example.test/apply",
        source="synthetic",
        source_posted_at=posted,
        is_active=True,
    )


SAMPLE = DiscoverResponse(
    items=[
        DiscoverItem(
            job=_job(JOB_A, datetime(2026, 10, 20, tzinfo=UTC)),
            match=JobMatch(
                required_total=2,
                required_matched=1,
                preferred_total=1,
                preferred_matched=1,
                coverage=0.5,
                matched_skills=[
                    SkillRequirement(skill_id=1, name="Python", requirement_type="REQUIRED"),
                    SkillRequirement(skill_id=3, name="Git", requirement_type="PREFERRED"),
                ],
                missing_skills=[
                    SkillRequirement(skill_id=2, name="Java", requirement_type="REQUIRED")
                ],
            ),
            rank=1,
        ),
        DiscoverItem(
            job=_job(JOB_B, None),
            match=JobMatch(
                required_total=0,
                required_matched=0,
                preferred_total=0,
                preferred_matched=0,
                coverage=None,
                matched_skills=[],
                missing_skills=[],
            ),
            rank=2,
        ),
    ],
    has_more=True,
)


class FakeStore:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.calls: list[tuple] = []
        self.profile = True

    def feed(self, user_id, filters, limit, offset):
        self.events.append("store")
        self.calls.append((user_id, filters, limit, offset))
        if not self.profile:
            raise DiscoverProfileMissing
        return SAMPLE


@pytest.fixture
def events() -> list[str]:
    return []


@pytest.fixture
def store(events: list[str]) -> Iterator[FakeStore]:
    fake = FakeStore(events)

    def fake_job_lock() -> Iterator[None]:
        events.append("lock")
        yield None
        events.append("unlock")

    app.dependency_overrides[get_discover_store] = lambda: fake
    app.dependency_overrides[get_authenticated_job_db] = fake_job_lock
    sign_in_as(ANA)
    yield fake
    app.dependency_overrides.pop(get_discover_store, None)
    app.dependency_overrides.pop(get_authenticated_job_db, None)
    app.dependency_overrides.pop(current_user, None)


def sign_in_as(user_id: UUID) -> None:
    app.dependency_overrides[current_user] = lambda: AuthenticatedUser(
        user_id=user_id, email=f"{user_id}@example.edu"
    )


def call(path: str) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(path)

    return asyncio.run(send())


def error(response: httpx.Response) -> dict[str, Any]:
    return response.json()["error"]


# --- success shape ---------------------------------------------------------


def test_response_shape_matches_api_md(store: FakeStore) -> None:
    response = call("/api/discover")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "has_more"}
    assert body["has_more"] is True
    first, second = body["items"]
    for item in (first, second):
        assert set(item) == {"job", "match", "rank"}
        assert set(item["job"]) == JOB_KEYS
        assert set(item["match"]) == MATCH_KEYS
    assert first["rank"] == 1
    assert first["job"]["job_id"] == JOB_A
    assert first["job"]["source_posted_at"] == "2026-10-20T00:00:00Z"
    assert first["job"]["work_arrangement"] is None
    assert first["match"]["coverage"] == 0.5
    assert first["match"]["matched_skills"] == [
        {"skill_id": 1, "name": "Python", "requirement_type": "REQUIRED"},
        {"skill_id": 3, "name": "Git", "requirement_type": "PREFERRED"},
    ]
    assert first["match"]["missing_skills"] == [
        {"skill_id": 2, "name": "Java", "requirement_type": "REQUIRED"}
    ]
    assert second["match"]["coverage"] is None
    assert second["match"]["matched_skills"] == []
    assert second["job"]["source_posted_at"] is None


def test_defaults_and_verified_user_reach_the_store(store: FakeStore) -> None:
    sign_in_as(BEN)
    assert call("/api/discover").status_code == 200
    assert store.calls == [(BEN, DiscoverFilters(), 20, 0)]


def test_filters_are_trimmed_and_passed_through(store: FakeStore) -> None:
    response = call(
        "/api/discover?job_type=INTERNSHIP&work_arrangement=REMOTE"
        "&location=%20Singapore%20&q=%20data%20&limit=5&offset=10"
    )
    assert response.status_code == 200
    assert store.calls == [
        (
            ANA,
            DiscoverFilters(
                job_type="INTERNSHIP", work_arrangement="REMOTE", location="Singapore", q="data"
            ),
            5,
            10,
        )
    ]


def test_blank_text_filters_are_treated_as_absent(store: FakeStore) -> None:
    assert call("/api/discover?location=%20%20&q=").status_code == 200
    assert store.calls[0][1] == DiscoverFilters()


def test_route_holds_the_job_read_lock_around_the_query(
    store: FakeStore, events: list[str]
) -> None:
    assert call("/api/discover").status_code == 200
    assert events == ["lock", "store", "unlock"]


# --- errors ----------------------------------------------------------------


def test_requires_a_token(store: FakeStore) -> None:
    app.dependency_overrides.pop(current_user, None)
    response = call("/api/discover")
    assert response.status_code == 401
    assert error(response)["code"] == "unauthenticated"
    assert store.calls == []


def test_no_profile_is_404_profile(store: FakeStore) -> None:
    store.profile = False
    response = call("/api/discover")
    assert response.status_code == 404
    assert error(response)["code"] == "not_found"
    assert error(response)["details"] == {"resource": "profile"}


@pytest.mark.parametrize(
    ("query", "field"),
    [
        ("limit=51", "limit"),
        ("limit=0", "limit"),
        ("limit=abc", "limit"),
        ("offset=-1", "offset"),
        ("offset=10001", "offset"),
        ("job_type=CONTRACT", "job_type"),
        ("job_type=internship", "job_type"),
        ("work_arrangement=OFFICE", "work_arrangement"),
        ("location=" + "x" * 101, "location"),
        ("q=" + "x" * 101, "q"),
        ("user_id=22222222-2222-4222-8222-222222222222", "user_id"),
        ("limlt=5", "limlt"),
    ],
)
def test_invalid_query_is_422(store: FakeStore, query: str, field: str) -> None:
    response = call(f"/api/discover?{query}")
    assert response.status_code == 422
    assert error(response)["code"] == "validation_failed"
    assert error(response)["details"] == {"field": field}
    assert store.calls == []


def test_limit_50_and_offset_10000_are_allowed(store: FakeStore) -> None:
    assert call("/api/discover?limit=50&offset=10000").status_code == 200
    assert store.calls[0][2:] == (50, 10000)
