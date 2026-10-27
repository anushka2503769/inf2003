"""Connection reuse in app.sql_db against a real PostgreSQL database.

Skipped unless TEST_DATABASE_URL points at a throwaway database (see
backend/scripts/run_disposable_db_tests.sh). Never point it at the team's
Supabase project.
"""

import os
import time
from collections.abc import Iterator

import psycopg2
import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="Set TEST_DATABASE_URL to a throwaway PostgreSQL database to run these.",
)

_LOCK_KEY = 2003999  # not the app's pipeline lock key


@pytest.fixture(autouse=True)
def database(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)

    from app import config, sql_db

    config.get_settings.cache_clear()
    sql_db.close_idle_connections()
    yield
    sql_db.close_idle_connections()
    config.get_settings.cache_clear()


def _pid(conn) -> int:
    with conn.cursor() as cursor:
        cursor.execute("SELECT pg_backend_pid()")
        return cursor.fetchone()[0]


def test_closed_connection_is_handed_out_again() -> None:
    from app.sql_db import get_pg_connection

    first = get_pg_connection()
    pid = _pid(first)
    first.close()

    second = get_pg_connection()
    try:
        assert second is first
        assert _pid(second) == pid
    finally:
        second.close()


def test_close_rolls_back_so_the_next_borrower_starts_clean() -> None:
    from app.sql_db import get_pg_connection

    conn = get_pg_connection()
    with conn.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout = '1s'")
        cursor.execute("CREATE TEMP TABLE pool_leak (x int)")
    conn.close()

    again = get_pg_connection()
    try:
        assert again is conn
        with again.cursor() as cursor:
            cursor.execute("SHOW lock_timeout")
            assert cursor.fetchone()[0] == "0"
            cursor.execute("SELECT to_regclass('pg_temp.pool_leak')")
            assert cursor.fetchone()[0] is None
    finally:
        again.close()


def test_close_releases_transaction_advisory_locks() -> None:
    from app.sql_db import get_pg_connection

    conn = get_pg_connection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", (_LOCK_KEY,))
    conn.close()

    other = psycopg2.connect(TEST_DATABASE_URL)
    try:
        with other.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", (_LOCK_KEY,))
            assert cursor.fetchone()[0] is True
    finally:
        other.close()


def test_connection_after_a_failed_statement_is_reusable() -> None:
    from app.sql_db import get_pg_connection

    conn = get_pg_connection()
    with pytest.raises(psycopg2.errors.DivisionByZero):
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 / 0")
    conn.close()

    again = get_pg_connection()
    try:
        assert again is conn
        with again.cursor() as cursor:
            cursor.execute("SELECT 1")
            assert cursor.fetchone()[0] == 1
    finally:
        again.close()


def test_connection_killed_by_the_server_is_discarded_not_reused() -> None:
    from app import sql_db

    conn = sql_db.get_pg_connection()
    pid = _pid(conn)  # leaves a transaction open, so close() must talk to the server
    killer = psycopg2.connect(TEST_DATABASE_URL)
    try:
        killer.autocommit = True
        with killer.cursor() as cursor:
            cursor.execute("SELECT pg_terminate_backend(%s)", (pid,))
    finally:
        killer.close()

    conn.close()
    assert conn.closed
    assert sql_db._idle == []

    fresh = sql_db.get_pg_connection()
    try:
        assert _pid(fresh) != pid
    finally:
        fresh.close()


def test_double_close_parks_the_connection_once() -> None:
    from app import sql_db

    conn = sql_db.get_pg_connection()
    conn.close()
    conn.close()
    assert sql_db._idle == [conn]

    first = sql_db.get_pg_connection()
    second = sql_db.get_pg_connection()
    try:
        assert first is conn
        assert second is not conn
    finally:
        first.close()
        second.close()


def test_idle_pool_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import sql_db

    monkeypatch.setattr(sql_db, "_MAX_IDLE", 1)
    kept = sql_db.get_pg_connection()
    extra = sql_db.get_pg_connection()
    kept.close()
    extra.close()

    assert sql_db._idle == [kept]
    assert extra.closed


def test_idle_connection_past_its_age_is_closed_not_reused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import sql_db

    conn = sql_db.get_pg_connection()
    conn.close()
    monkeypatch.setattr(sql_db, "_MAX_IDLE_SECONDS", 0.0)

    fresh = sql_db.get_pg_connection()
    try:
        assert fresh is not conn
        assert conn.closed
    finally:
        fresh.close()


@pytest.mark.parametrize("shift", [-3600.0, 3600.0], ids=["parked-an-hour-ago", "clock-set-back"])
def test_idle_age_is_wall_clock_and_rejects_out_of_range_ages(shift: float) -> None:
    from app import sql_db

    conn = sql_db.get_pg_connection()
    conn.close()
    # Wall-clock timestamps, so time spent asleep counts towards the idle age.
    assert abs(conn._idle_since - time.time()) < 5
    conn._idle_since += shift

    fresh = sql_db.get_pg_connection()
    try:
        assert fresh is not conn
        assert conn.closed
    finally:
        fresh.close()


def test_connection_for_another_database_url_is_not_reused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import config, sql_db

    conn = sql_db.get_pg_connection()
    conn.close()

    separator = "&" if "?" in TEST_DATABASE_URL else "?"
    monkeypatch.setenv("DATABASE_URL", f"{TEST_DATABASE_URL}{separator}application_name=other")
    config.get_settings.cache_clear()

    other = sql_db.get_pg_connection()
    try:
        assert other is not conn
        assert conn.closed
    finally:
        other.close()
