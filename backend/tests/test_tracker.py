"""Tracker route tests with a fake store (no database).

The SQL behaviour is covered in test_tracker_sql.py. Here the point is the
HTTP contract in docs/API.md section 6: status codes, shapes, validation and
that the store only ever sees the verified user id.
"""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

from app.auth import AuthenticatedUser, current_user
from app.main import app
from app.schemas import JobSummary, TrackerItem
from app.sql_tracker import (
    TRACKER_STATUSES,
    TrackerJobMissing,
    TrackerProfileMissing,
    get_tracker_store,
)

ANA = UUID("11111111-1111-4111-8111-111111111111")
BEN = UUID("22222222-2222-4222-8222-222222222222")
JOB = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)


def _item(job_id: UUID, status: str) -> TrackerItem:
    return TrackerItem(
        job=JobSummary(
            job_id=str(job_id),
            title="Engineer",
            company_name="Acme",
            location=None,
            job_type="INTERNSHIP",
            work_arrangement=None,
            application_url="https://example.test/apply",
            source="synthetic",
            source_posted_at=None,
            is_active=True,
        ),
        status=status,
        created_at=NOW,
        updated_at=NOW,
    )


class FakeStore:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.profile = True
        self.job_exists = True
        self.items: list[TrackerItem] = []
        self.total = 0

    def put(self, user_id, job_id, status):
        self.calls.append(("put", user_id, job_id, status))
        if not self.profile:
            raise TrackerProfileMissing
        if not self.job_exists:
            raise TrackerJobMissing
        return _item(job_id, status)

    def list_items(self, user_id, statuses, limit, offset):
        self.calls.append(("list", user_id, statuses, limit, offset))
        return self.items, self.total

    def summary(self, user_id):
        self.calls.append(("summary", user_id))
        return {**dict.fromkeys(TRACKER_STATUSES, 0), "SAVED": 2}

    def delete(self, user_id, job_id):
        self.calls.append(("delete", user_id, job_id))
        if not self.profile:
            raise TrackerProfileMissing


@pytest.fixture
def store() -> Iterator[FakeStore]:
    fake = FakeStore()
    app.dependency_overrides[get_tracker_store] = lambda: fake
    app.dependency_overrides[current_user] = lambda: AuthenticatedUser(
        user_id=ANA, email="ana@example.edu"
    )
    yield fake
    app.dependency_overrides.pop(get_tracker_store, None)
    app.dependency_overrides.pop(current_user, None)


def call(method: str, path: str, json: Any = None) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, json=json)

    return asyncio.run(send())


def test_put_returns_the_tracker_item_with_the_api_shape(store: FakeStore) -> None:
    response = call("PUT", f"/api/me/jobs/{JOB}", {"status": "SAVED"})
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"job", "status", "created_at", "updated_at"}
    assert set(payload["job"]) == {
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
    assert payload["status"] == "SAVED"
    assert payload["job"]["job_id"] == str(JOB)
    assert payload["job"]["location"] is None


def test_put_unknown_or_inactive_job_is_404_job(store: FakeStore) -> None:
    store.job_exists = False
    response = call("PUT", f"/api/me/jobs/{JOB}", {"status": "SAVED"})
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["details"] == {"resource": "job"}


def test_put_without_profile_is_404_profile(store: FakeStore) -> None:
    store.profile = False
    response = call("PUT", f"/api/me/jobs/{JOB}", {"status": "SAVED"})
    assert response.status_code == 404
    assert response.json()["error"]["details"] == {"resource": "profile"}


@pytest.mark.parametrize(
    ("path", "body", "field"),
    [
        ("/api/me/jobs/not-a-uuid", {"status": "SAVED"}, "job_id"),
        (f"/api/me/jobs/{JOB}", {"status": "MAYBE"}, "status"),
        (f"/api/me/jobs/{JOB}", {}, "status"),
    ],
)
def test_put_validation(store: FakeStore, path: str, body: dict, field: str) -> None:
    response = call("PUT", path, body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"
    assert response.json()["error"]["details"]["field"] == field
    assert store.calls == []


def test_get_list_shape_and_defaults(store: FakeStore) -> None:
    store.items = [_item(JOB, "APPLIED")]
    store.total = 7
    response = call("GET", "/api/me/jobs")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"items", "total"}
    assert payload["total"] == 7
    assert payload["items"][0]["status"] == "APPLIED"
    assert store.calls == [("list", ANA, None, 20, 0)]


def test_get_list_passes_repeated_status_filters(store: FakeStore) -> None:
    call("GET", "/api/me/jobs?status=SAVED&status=APPLIED&limit=5&offset=10")
    assert store.calls == [("list", ANA, ["SAVED", "APPLIED"], 5, 10)]


@pytest.mark.parametrize(
    "query",
    [
        "status=MAYBE",
        "limit=0",
        "limit=51",
        "limit=abc",
        "offset=-1",
        "offset=10001",
        "limlt=5",
    ],
)
def test_get_list_rejects_bad_query(store: FakeStore, query: str) -> None:
    response = call("GET", f"/api/me/jobs?{query}")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"
    assert store.calls == []


def test_summary_shape_has_every_status(store: FakeStore) -> None:
    response = call("GET", "/api/me/jobs/summary")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"counts", "total"}
    assert set(payload["counts"]) == set(TRACKER_STATUSES)
    assert payload["counts"]["SAVED"] == 2
    assert payload["total"] == 2


def test_delete_is_204_and_without_profile_404(store: FakeStore) -> None:
    response = call("DELETE", f"/api/me/jobs/{JOB}")
    assert response.status_code == 204
    assert response.content == b""
    store.profile = False
    response = call("DELETE", f"/api/me/jobs/{JOB}")
    assert response.status_code == 404
    assert response.json()["error"]["details"] == {"resource": "profile"}


def test_delete_bad_uuid_is_422(store: FakeStore) -> None:
    assert call("DELETE", "/api/me/jobs/nope").status_code == 422


def test_requires_a_token(store: FakeStore) -> None:
    app.dependency_overrides.pop(current_user, None)
    assert call("GET", "/api/me/jobs").status_code == 401


def test_store_only_receives_the_verified_user_id(store: FakeStore) -> None:
    """A user_id in the body or query is ignored; the token subject is used."""
    call("PUT", f"/api/me/jobs/{JOB}", {"status": "SAVED", "user_id": str(BEN)})
    call("GET", f"/api/me/jobs?user_id={BEN}")  # rejected as unknown parameter
    call("GET", "/api/me/jobs")
    call("GET", "/api/me/jobs/summary")
    call("DELETE", f"/api/me/jobs/{uuid4()}")
    assert store.calls
    assert all(call_[1] == ANA for call_ in store.calls)


def test_put_and_delete_reject_unknown_query_parameters(store: FakeStore) -> None:
    put = call("PUT", f"/api/me/jobs/{JOB}?unexpected=1", {"status": "SAVED"})
    delete = call("DELETE", f"/api/me/jobs/{JOB}?unexpected=1")
    for response in (put, delete):
        assert response.status_code == 422
        assert response.json()["error"]["details"] == {"field": "unexpected"}
    assert store.calls == []


def _pg_error(cls: type, constraint: str | None) -> Exception:
    """A psycopg2-style error whose diag reports the given constraint name."""

    class Diag:
        constraint_name = constraint

    class Error(cls):  # type: ignore[valid-type, misc]
        diag = Diag()

    return Error("synthetic")


@pytest.mark.parametrize(
    ("cls_name", "constraint", "expected"),
    [
        ("ForeignKeyViolation", "user_jobs_user_id_fkey", "profile"),
        ("ForeignKeyViolation", "user_jobs_job_id_fkey", "job"),
        ("ForeignKeyViolation", "something_else", None),
        ("CheckViolation", None, "trigger"),
        ("CheckViolation", "user_jobs_status_check", None),
    ],
)
def test_classify_put_failure_uses_the_original_constraint(
    cls_name: str, constraint: str | None, expected: str | None
) -> None:
    from psycopg2 import errors

    from app.sql_tracker import classify_put_failure

    assert classify_put_failure(_pg_error(getattr(errors, cls_name), constraint)) == expected
