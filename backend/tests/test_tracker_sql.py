"""Tracker routes against a real database.

Skipped unless TEST_DATABASE_URL is set (see tests/test_sql_profile.py). The
database must be throwaway with migrations 001 and 003 applied. These go
through the HTTP routes so the contract is checked end to end.
"""

import asyncio
import os
import time
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import httpx
import psycopg2
import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="Set TEST_DATABASE_URL to a throwaway PostgreSQL database to run these.",
)

ANA = UUID("11111111-1111-4111-8111-111111111111")
BEN = UUID("22222222-2222-4222-8222-222222222222")
NOBODY = UUID("33333333-3333-4333-8333-333333333333")

STATUSES = ["NOT_INTERESTED", "SAVED", "APPLIED", "INTERVIEW", "REJECTED", "OFFER"]


def _open() -> psycopg2.extensions.connection:
    return psycopg2.connect(TEST_DATABASE_URL)


def _reset() -> None:
    conn = _open()
    try:
        with conn.cursor() as cursor:
            cursor.execute("TRUNCATE public.users, public.jobs CASCADE")
            cursor.execute("DELETE FROM auth.users")
        conn.commit()
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def database(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    from app import config

    config.get_settings.cache_clear()
    _reset()
    _sign_up(ANA, "Ana Lim")
    _sign_up(BEN, "Ben Tan")
    yield
    _reset()
    config.get_settings.cache_clear()


def _sign_up(user_id: UUID, full_name: str) -> None:
    conn = _open()
    try:
        with conn.cursor() as cursor:
            cursor.execute("INSERT INTO auth.users (id) VALUES (%s)", (str(user_id),))
            cursor.execute(
                "INSERT INTO public.users (user_id, full_name) VALUES (%s, %s)",
                (str(user_id), full_name),
            )
        conn.commit()
    finally:
        conn.close()


def _job(*, active: bool = True, title: str = "Engineer") -> str:
    conn = _open()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO public.jobs (source, external_job_id, title, company_name,
                                         application_url, is_active)
                VALUES ('synthetic', %s, %s, 'Acme', 'https://example.test', %s)
                RETURNING job_id
                """,
                (str(uuid4()), title, active),
            )
            job_id = str(cursor.fetchone()[0])
        conn.commit()
        return job_id
    finally:
        conn.close()


def _set_active(job_id: str, active: bool) -> None:
    conn = _open()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE public.jobs SET is_active = %s WHERE job_id = %s", (active, job_id)
            )
        conn.commit()
    finally:
        conn.close()


def _row_count(user_id: UUID) -> int:
    conn = _open()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM public.user_jobs WHERE user_id = %s", (str(user_id),)
            )
            return cursor.fetchone()[0]
    finally:
        conn.close()


def call(method: str, path: str, json: Any = None, user_id: UUID = ANA) -> httpx.Response:
    from app.auth import AuthenticatedUser, current_user
    from app.main import app

    app.dependency_overrides[current_user] = lambda: AuthenticatedUser(
        user_id=user_id, email=f"{user_id}@example.edu"
    )

    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, json=json)

    try:
        return asyncio.run(send())
    finally:
        app.dependency_overrides.pop(current_user, None)


def put(job_id: str, status: str, user_id: UUID = ANA) -> httpx.Response:
    return call("PUT", f"/api/me/jobs/{job_id}", {"status": status}, user_id)


def test_put_creates_and_returns_the_item() -> None:
    job_id = _job(title="Data Intern")
    response = put(job_id, "SAVED")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "SAVED"
    assert payload["job"]["job_id"] == job_id
    assert payload["job"]["title"] == "Data Intern"
    assert payload["job"]["is_active"] is True
    assert payload["created_at"] and payload["updated_at"]


def test_repeat_put_is_a_noop_that_keeps_updated_at() -> None:
    job_id = _job()
    first = put(job_id, "SAVED").json()
    time.sleep(0.05)
    second = put(job_id, "SAVED")
    assert second.status_code == 200
    assert second.json()["updated_at"] == first["updated_at"]
    assert second.json()["created_at"] == first["created_at"]
    assert _row_count(ANA) == 1


def test_status_change_bumps_updated_at_but_not_created_at() -> None:
    job_id = _job()
    first = put(job_id, "SAVED").json()
    time.sleep(0.05)
    second = put(job_id, "APPLIED").json()
    assert second["status"] == "APPLIED"
    assert second["updated_at"] > first["updated_at"]
    assert second["created_at"] == first["created_at"]


def test_inactive_or_unknown_job_is_not_found_on_create() -> None:
    inactive = _job(active=False)
    for job_id in (inactive, str(uuid4())):
        response = put(job_id, "SAVED")
        assert response.status_code == 404
        assert response.json()["error"]["details"] == {"resource": "job"}
    assert _row_count(ANA) == 0


def test_updating_an_existing_row_is_allowed_after_the_job_goes_inactive() -> None:
    job_id = _job()
    put(job_id, "SAVED")
    _set_active(job_id, False)
    response = put(job_id, "APPLIED")
    assert response.status_code == 200
    assert response.json()["status"] == "APPLIED"
    assert response.json()["job"]["is_active"] is False


def test_put_without_profile_is_404_profile() -> None:
    job_id = _job()
    response = put(job_id, "SAVED", user_id=NOBODY)
    assert response.status_code == 404
    assert response.json()["error"]["details"] == {"resource": "profile"}
    # Even for an inactive job the missing profile is what is reported.
    response = put(_job(active=False), "SAVED", user_id=NOBODY)
    assert response.json()["error"]["details"] == {"resource": "profile"}


def test_delete_twice_is_204_twice_and_removes_the_row() -> None:
    job_id = _job()
    put(job_id, "SAVED")
    assert call("DELETE", f"/api/me/jobs/{job_id}").status_code == 204
    assert _row_count(ANA) == 0
    assert call("DELETE", f"/api/me/jobs/{job_id}").status_code == 204
    # Never tracked at all is also fine.
    assert call("DELETE", f"/api/me/jobs/{uuid4()}").status_code == 204


def test_delete_without_profile_is_404_profile() -> None:
    response = call("DELETE", f"/api/me/jobs/{_job()}", user_id=NOBODY)
    assert response.status_code == 404
    assert response.json()["error"]["details"] == {"resource": "profile"}


def test_users_cannot_see_or_change_each_others_rows() -> None:
    job_id = _job()
    put(job_id, "SAVED", user_id=ANA)

    assert call("GET", "/api/me/jobs", user_id=BEN).json() == {"items": [], "total": 0}
    summary = call("GET", "/api/me/jobs/summary", user_id=BEN).json()
    assert summary["total"] == 0

    # Ben deleting or putting the same job touches only Ben's own row.
    assert call("DELETE", f"/api/me/jobs/{job_id}", user_id=BEN).status_code == 204
    ana_items = call("GET", "/api/me/jobs", user_id=ANA).json()
    assert [item["status"] for item in ana_items["items"]] == ["SAVED"]

    put(job_id, "OFFER", user_id=BEN)
    ana_items = call("GET", "/api/me/jobs", user_id=ANA).json()
    assert [item["status"] for item in ana_items["items"]] == ["SAVED"]
    assert call("GET", "/api/me/jobs", user_id=BEN).json()["total"] == 1


def test_summary_has_all_six_statuses_with_zeros() -> None:
    empty = call("GET", "/api/me/jobs/summary").json()
    assert empty == {"counts": dict.fromkeys(STATUSES, 0), "total": 0}

    for status in ("SAVED", "SAVED", "APPLIED"):
        put(_job(), status)
    summary = call("GET", "/api/me/jobs/summary").json()
    assert list(summary["counts"]) == STATUSES or set(summary["counts"]) == set(STATUSES)
    assert summary["counts"]["SAVED"] == 2
    assert summary["counts"]["APPLIED"] == 1
    assert summary["counts"]["OFFER"] == 0
    assert summary["total"] == 3


def test_list_filters_by_multiple_statuses_orders_and_counts() -> None:
    a, b, c, d = (_job(title=name) for name in ("A", "B", "C", "D"))
    for job_id, status in ((a, "SAVED"), (b, "APPLIED"), (c, "REJECTED"), (d, "SAVED")):
        put(job_id, status)
        time.sleep(0.02)
    # Touch A last so it becomes the most recently updated.
    put(a, "INTERVIEW")

    everything = call("GET", "/api/me/jobs").json()
    assert everything["total"] == 4
    assert [i["job"]["title"] for i in everything["items"]] == ["A", "D", "C", "B"]

    filtered = call("GET", "/api/me/jobs?status=SAVED&status=APPLIED").json()
    assert filtered["total"] == 2
    assert [i["job"]["title"] for i in filtered["items"]] == ["D", "B"]

    page = call("GET", "/api/me/jobs?limit=1&offset=1").json()
    assert page["total"] == 4
    assert [i["job"]["title"] for i in page["items"]] == ["D"]


def test_total_is_correct_when_the_page_is_past_the_end() -> None:
    for _ in range(3):
        put(_job(), "SAVED")
    past = call("GET", "/api/me/jobs?offset=50").json()
    assert past == {"items": [], "total": 3}
    past = call("GET", "/api/me/jobs?status=APPLIED&offset=5").json()
    assert past == {"items": [], "total": 0}


def test_ties_on_updated_at_order_by_job_id() -> None:
    """Rows written in one transaction share now(), so job_id breaks the tie."""
    jobs = sorted(_job() for _ in range(3))
    conn = _open()
    try:
        with conn.cursor() as cursor:
            for job_id in reversed(jobs):
                cursor.execute(
                    "INSERT INTO public.user_jobs (user_id, job_id, status)"
                    " VALUES (%s, %s, 'SAVED')",
                    (str(ANA), job_id),
                )
        conn.commit()
    finally:
        conn.close()
    items = call("GET", "/api/me/jobs").json()["items"]
    assert [i["job"]["job_id"] for i in items] == jobs
