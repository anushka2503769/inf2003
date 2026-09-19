"""PostgresProfileStore against a real PostgreSQL database.

These tests are skipped unless TEST_DATABASE_URL is set, so CI and teammates
without a database still get a green suite. TEST_DATABASE_URL must point at a
throwaway database: the fixtures truncate public.users and the rows that
reference it. Never point it at the team's Supabase project.

A deliberately separate variable from DATABASE_URL, so running the suite with a
normal backend/.env cannot delete real profiles.
"""

import os
import threading
import time
from collections.abc import Iterator
from uuid import UUID, uuid4

import psycopg2
import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="Set TEST_DATABASE_URL to a throwaway PostgreSQL database to run these.",
)

ANA = UUID("11111111-1111-4111-8111-111111111111")
BEN = UUID("22222222-2222-4222-8222-222222222222")


@pytest.fixture(autouse=True)
def database(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point the store at the test database and clear it between tests."""
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)

    from app import config

    # sql_db.get_pg_connection reads settings on every call, so clearing the
    # cache after setting the variable is what points the store at the test
    # database. No patching of the connection function is involved.
    config.get_settings.cache_clear()

    _reset()
    yield
    _reset()
    config.get_settings.cache_clear()


def _open() -> psycopg2.extensions.connection:
    return psycopg2.connect(TEST_DATABASE_URL)


def _reset() -> None:
    conn = _open()
    try:
        with conn.cursor() as cursor:
            cursor.execute("TRUNCATE public.users CASCADE")
            cursor.execute("DELETE FROM auth.users")
        conn.commit()
    finally:
        conn.close()


def _sign_up(user_id: UUID) -> None:
    """Create the auth.users row Supabase would create at Google sign-in."""
    conn = _open()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO auth.users (id) VALUES (%s) ON CONFLICT DO NOTHING",
                (str(user_id),),
            )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def store():
    from app.sql_profile import PostgresProfileStore

    return PostgresProfileStore()


def test_reading_before_onboarding_returns_nothing(store) -> None:
    assert store.get(ANA) is None


def test_onboarding_creates_the_row(store) -> None:
    _sign_up(ANA)
    profile = store.upsert(ANA, "Ana Lim")
    assert profile.user_id == ANA
    assert profile.full_name == "Ana Lim"
    assert store.get(ANA) == profile


def test_onboarding_is_safe_to_retry(store) -> None:
    """A retry after a lost response must not duplicate or reset the profile."""
    _sign_up(ANA)
    first = store.upsert(ANA, "Ana Lim")
    second = store.upsert(ANA, "Ana Lim")
    assert second.created_at == first.created_at
    assert _row_count() == 1


def test_delayed_onboarding_retry_preserves_a_renamed_profile(store) -> None:
    _sign_up(ANA)
    created = store.upsert(ANA, "Ana Lim")
    renamed = store.update_name(ANA, "Ana Tan")
    assert renamed is not None

    retried = store.upsert(ANA, "Ana Lim")

    assert retried.full_name == "Ana Tan"
    assert retried.created_at == created.created_at
    assert retried.updated_at == renamed.updated_at


def test_renaming_moves_updated_at_and_keeps_created_at(store) -> None:
    _sign_up(ANA)
    created = store.upsert(ANA, "Ana Lim")
    renamed = store.update_name(ANA, "Ana Tan")
    assert renamed is not None
    assert renamed.full_name == "Ana Tan"
    assert renamed.created_at == created.created_at
    assert renamed.updated_at > created.updated_at


def test_renaming_to_the_same_name_does_not_move_updated_at(store) -> None:
    """docs/API.md: update updated_at only if the stored name changes."""
    _sign_up(ANA)
    created = store.upsert(ANA, "Ana Lim")
    unchanged = store.update_name(ANA, "Ana Lim")
    assert unchanged is not None
    assert unchanged.updated_at == created.updated_at


def test_renaming_before_onboarding_returns_nothing(store) -> None:
    assert store.update_name(ANA, "Ana Lim") is None
    assert _row_count() == 0


def test_students_are_isolated(store) -> None:
    _sign_up(ANA)
    _sign_up(BEN)
    store.upsert(ANA, "Ana Lim")
    store.upsert(BEN, "Ben Ong")
    store.update_name(BEN, "Benjamin Ong")

    ana = store.get(ANA)
    assert ana is not None and ana.full_name == "Ana Lim"


def test_unknown_auth_account_is_refused_without_leaking_sql(store) -> None:
    """The users.user_id foreign key must not be reported as a student error."""
    from app.sql_access import SqlAccessError

    with pytest.raises(SqlAccessError) as caught:
        store.upsert(uuid4(), "Nobody")

    message = str(caught.value)
    assert "authentication store" in message
    for leak in ("psycopg2", "INSERT", "public.users", "DETAIL"):
        assert leak not in message
    assert _row_count() == 0


def test_simultaneous_first_logins_create_one_profile(store) -> None:
    """Two devices finishing onboarding at once must not produce two rows.

    docs/API.md: handle simultaneous calls atomically using the primary-key
    conflict. A check-then-insert would let several callers all see "no row"
    and then collide.
    """
    _sign_up(ANA)
    workers = 8
    start = threading.Barrier(workers)
    profiles: list = []
    failures: list = []

    def onboard(n: int) -> None:
        start.wait(timeout=5)
        try:
            profiles.append(store.upsert(ANA, f"Ana {n}"))
        except BaseException as exc:  # noqa: BLE001 - the test reports whatever escaped
            failures.append(exc)

    threads = [threading.Thread(target=onboard, args=(n,)) for n in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not failures, f"concurrent onboarding raised: {failures}"
    assert len(profiles) == workers
    assert _row_count() == 1
    # created_at is never part of the conflict update, so every caller sees the
    # creation time of whichever transaction won.
    assert len({profile.created_at for profile in profiles}) == 1
    assert len({profile.full_name for profile in profiles}) == 1
    assert len({profile.updated_at for profile in profiles}) == 1


def test_upsert_waits_for_a_competing_insert(store) -> None:
    """The conflict branch, forced deterministically rather than by luck.

    An uncommitted insert holds the primary key, so a second writer blocks
    until it commits and must then take the update path instead of failing.
    """
    _sign_up(ANA)
    blocker = _open()
    outcome: dict = {}
    try:
        with blocker.cursor() as cursor:
            cursor.execute(
                "INSERT INTO public.users (user_id, full_name)"
                " VALUES (%s, %s) RETURNING created_at, updated_at",
                (str(ANA), "First Writer"),
            )
            first_created_at, first_updated_at = cursor.fetchone()

        def second_writer() -> None:
            try:
                outcome["profile"] = store.upsert(ANA, "Second Writer")
            except BaseException as exc:  # noqa: BLE001 - reported by the assertions below
                outcome["error"] = exc

        thread = threading.Thread(target=second_writer)
        thread.start()
        time.sleep(0.3)
        assert thread.is_alive(), "the second write should wait for the competing insert"

        blocker.commit()
        thread.join(timeout=10)
        assert not thread.is_alive(), "the second write never completed"
    finally:
        blocker.close()

    assert "error" not in outcome, f"the conflict was not handled: {outcome.get('error')}"
    profile = outcome["profile"]
    assert profile.full_name == "First Writer"
    assert profile.created_at == first_created_at
    assert profile.updated_at == first_updated_at
    assert _row_count() == 1


def _row_count() -> int:
    conn = _open()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM public.users")
            return cursor.fetchone()[0]
    finally:
        conn.close()
