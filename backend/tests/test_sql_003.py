"""Migration 003 (views, triggers, indexes) against a real PostgreSQL database.

Skipped unless TEST_DATABASE_URL is set (see tests/test_sql_profile.py). The
database must be throwaway with 001 and 003 applied: fixtures truncate the
application tables. Use backend/scripts/run_disposable_db_tests.sh.
"""

import os
import time
from collections.abc import Iterator
from uuid import uuid4

import psycopg2
import pytest
from psycopg2 import errors

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="Set TEST_DATABASE_URL to a throwaway PostgreSQL database to run these.",
)

CHECK_VIOLATION = "23514"


@pytest.fixture
def conn() -> Iterator["psycopg2.extensions.connection"]:
    connection = psycopg2.connect(TEST_DATABASE_URL)
    connection.autocommit = True  # every statement is its own transaction
    _reset(connection)
    yield connection
    _reset(connection)
    connection.close()


def _reset(connection) -> None:
    with connection.cursor() as cur:
        cur.execute("TRUNCATE public.users, public.jobs, public.skills CASCADE")
        cur.execute("DELETE FROM auth.users")


def _user(connection, name: str = "Test User") -> str:
    user_id = str(uuid4())
    with connection.cursor() as cur:
        cur.execute("INSERT INTO auth.users (id) VALUES (%s)", (user_id,))
        cur.execute(
            "INSERT INTO public.users (user_id, full_name) VALUES (%s, %s)",
            (user_id, name),
        )
    return user_id


def _job(
    connection,
    *,
    active: bool = True,
    job_type: str = "INTERNSHIP",
    arrangement: str = "REMOTE",
) -> str:
    with connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO public.jobs (source, external_job_id, title, company_name,
                                     application_url, job_type, work_arrangement,
                                     is_active)
            VALUES ('synthetic', %s, 'Engineer', 'Acme', 'https://example.test',
                    %s, %s, %s)
            RETURNING job_id
            """,
            (str(uuid4()), job_type, arrangement, active),
        )
        return str(cur.fetchone()[0])


def _skill(connection, name: str) -> int:
    with connection.cursor() as cur:
        cur.execute("INSERT INTO public.skills (name) VALUES (%s) RETURNING skill_id", (name,))
        return cur.fetchone()[0]


def _track(connection, user_id: str, job_id: str, status: str = "SAVED") -> None:
    with connection.cursor() as cur:
        cur.execute(
            "INSERT INTO public.user_jobs (user_id, job_id, status) VALUES (%s, %s, %s)",
            (user_id, job_id, status),
        )


def _scalar(connection, sql: str, params: tuple = ()):
    with connection.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()[0]


# --- updated_at trigger ---------------------------------------------------


def test_users_updated_at_changes_only_on_real_change(conn) -> None:
    user_id = _user(conn)
    query = "SELECT updated_at FROM public.users WHERE user_id = %s"
    original = _scalar(conn, query, (user_id,))
    time.sleep(0.05)  # autocommit: each statement has its own now()

    with conn.cursor() as cur:
        cur.execute("UPDATE public.users SET full_name = full_name WHERE user_id = %s", (user_id,))
    assert _scalar(conn, query, (user_id,)) == original

    with conn.cursor() as cur:
        cur.execute("UPDATE public.users SET full_name = 'Renamed' WHERE user_id = %s", (user_id,))
    assert _scalar(conn, query, (user_id,)) > original


def test_user_jobs_updated_at_changes_only_on_real_change(conn) -> None:
    user_id, job_id = _user(conn), _job(conn)
    _track(conn, user_id, job_id, "SAVED")
    query = "SELECT updated_at FROM public.user_jobs WHERE user_id = %s AND job_id = %s"
    original = _scalar(conn, query, (user_id, job_id))
    time.sleep(0.05)

    with conn.cursor() as cur:
        cur.execute("UPDATE public.user_jobs SET status = 'SAVED' WHERE user_id = %s", (user_id,))
    assert _scalar(conn, query, (user_id, job_id)) == original

    with conn.cursor() as cur:
        cur.execute("UPDATE public.user_jobs SET status = 'APPLIED' WHERE user_id = %s", (user_id,))
    assert _scalar(conn, query, (user_id, job_id)) > original


# --- user_jobs_requires_active_job ---------------------------------------


def test_insert_for_inactive_job_is_check_violation(conn) -> None:
    user_id, job_id = _user(conn), _job(conn, active=False)
    with pytest.raises(errors.CheckViolation) as excinfo:
        _track(conn, user_id, job_id)
    assert excinfo.value.pgcode == CHECK_VIOLATION
    assert _scalar(conn, "SELECT count(*) FROM public.user_jobs") == 0


def test_update_after_job_deactivated_is_allowed(conn) -> None:
    user_id, job_id = _user(conn), _job(conn)
    _track(conn, user_id, job_id, "SAVED")
    with conn.cursor() as cur:
        cur.execute("UPDATE public.jobs SET is_active = false WHERE job_id = %s", (job_id,))
        cur.execute("UPDATE public.user_jobs SET status = 'APPLIED' WHERE user_id = %s", (user_id,))
    assert (
        _scalar(conn, "SELECT status FROM public.user_jobs WHERE user_id = %s", (user_id,))
        == "APPLIED"
    )


# --- views ---------------------------------------------------------------


def test_requirement_counts_view(conn) -> None:
    active, inactive = _job(conn), _job(conn, active=False)
    py, sql, git = _skill(conn, "Python"), _skill(conn, "SQL"), _skill(conn, "Git")
    with conn.cursor() as cur:
        for job_id, skill_id, kind in [
            (active, py, "REQUIRED"),
            (active, sql, "REQUIRED"),
            (active, git, "PREFERRED"),
            (inactive, py, "REQUIRED"),
        ]:
            cur.execute(
                "INSERT INTO public.job_skills VALUES (%s, %s, %s)", (job_id, skill_id, kind)
            )
        cur.execute(
            "SELECT job_id::text, required_total, preferred_total "
            "FROM public.v_job_requirement_counts"
        )
        assert cur.fetchall() == [(active, 2, 1)]


def test_tracker_summary_view(conn) -> None:
    ana, ben = _user(conn, "Ana"), _user(conn, "Ben")
    jobs = [_job(conn) for _ in range(3)]
    _track(conn, ana, jobs[0], "SAVED")
    _track(conn, ana, jobs[1], "SAVED")
    _track(conn, ana, jobs[2], "APPLIED")
    _track(conn, ben, jobs[0], "OFFER")
    with conn.cursor() as cur:
        cur.execute("SELECT user_id::text, status, job_count FROM public.v_user_tracker_summary")
        assert sorted(cur.fetchall()) == sorted(
            [(ana, "SAVED", 2), (ana, "APPLIED", 1), (ben, "OFFER", 1)]
        )


# --- privileges ----------------------------------------------------------


@pytest.mark.parametrize("view", ["v_job_requirement_counts", "v_user_tracker_summary"])
def test_view_privileges(conn, view: str) -> None:
    with conn.cursor() as cur:
        for role in ("anon", "authenticated"):
            cur.execute(f"SET ROLE {role}")
            with pytest.raises(errors.InsufficientPrivilege):
                cur.execute(f"SELECT * FROM public.{view}")
            cur.execute("RESET ROLE")
        cur.execute("SET ROLE service_role")
        cur.execute(f"SELECT * FROM public.{view}")  # allowed
        cur.execute("RESET ROLE")


# --- indexes -------------------------------------------------------------


def test_partial_indexes_are_used_for_active_job_queries(conn) -> None:
    """Prove the partial indexes are usable and chosen by the planner.

    Tiny tables make the planner prefer a sequential scan, so the test turns
    enable_seqscan off for the session (autocommit, so SET is session-wide and
    reset in finally). That shows the index is eligible and selected, not that
    the planner would pick it on this tiny fixture without the hint.
    """
    for i in range(30):
        _job(
            conn,
            active=i % 3 != 0,
            job_type="INTERNSHIP" if i % 2 else "FULL_TIME",
            arrangement="REMOTE" if i % 5 else "ONSITE",
        )
    with conn.cursor() as cur:
        cur.execute("ANALYZE public.jobs")
        cur.execute("SET enable_seqscan = off")
        try:
            cur.execute(
                "EXPLAIN SELECT job_id FROM public.jobs "
                "WHERE is_active AND job_type = 'INTERNSHIP' "
                "AND work_arrangement = 'REMOTE'"
            )
            filter_plan = "\n".join(row[0] for row in cur.fetchall())
            cur.execute(
                "EXPLAIN SELECT job_id FROM public.jobs WHERE is_active "
                "ORDER BY source_posted_at DESC LIMIT 5"
            )
            order_plan = "\n".join(row[0] for row in cur.fetchall())
        finally:
            cur.execute("RESET enable_seqscan")
    assert "jobs_active_type_arrangement_idx" in filter_plan
    assert "jobs_active_posted_at_idx" in order_plan
