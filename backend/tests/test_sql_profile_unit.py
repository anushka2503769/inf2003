"""Offline transaction tests for the PostgreSQL profile store."""

from datetime import UTC, datetime
from uuid import UUID

import psycopg2
import pytest

from app.sql_access import SqlAccessError
from app.sql_profile import PostgresProfileStore

ANA = UUID("11111111-1111-4111-8111-111111111111")
CREATED = datetime(2026, 9, 19, 8, 0, tzinfo=UTC)
UPDATED = datetime(2026, 9, 19, 9, 0, tzinfo=UTC)


class _Cursor:
    def __init__(
        self,
        *,
        inserted_row: tuple | None,
        profile_row: tuple | None,
        skills_rows: list[tuple] | None = None,
        fail_on_skills_read: bool = False,
    ) -> None:
        self.inserted_row = inserted_row
        self.profile_row = profile_row
        self.skills_rows = skills_rows or []
        self.fail_on_skills_read = fail_on_skills_read
        self.statements: list[tuple[str, tuple]] = []
        self._last_query = ""

    def execute(self, query: str, parameters: tuple = ()) -> None:
        self.statements.append((query, parameters))
        self._last_query = query
        if self.fail_on_skills_read and "JOIN public.skills" in query:
            raise psycopg2.OperationalError("synthetic skills read failed")

    def fetchone(self) -> tuple | None:
        if "INSERT INTO public.users" in self._last_query:
            return self.inserted_row
        if "SELECT user_id, full_name, created_at, updated_at" in self._last_query:
            return self.profile_row
        raise AssertionError(f"unexpected fetchone query: {self._last_query}")

    def fetchall(self) -> list[tuple]:
        assert "JOIN public.skills" in self._last_query
        return self.skills_rows

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *_: object) -> bool:
        return False


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self.cursor_obj = cursor
        self.commit_calls = 0
        self.rollback_calls = 0
        self.closed = False

    def cursor(self) -> _Cursor:
        return self.cursor_obj

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1

    def close(self) -> None:
        self.closed = True


def test_upsert_with_skills_preserves_existing_row_on_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = _Cursor(
        inserted_row=None,
        profile_row=(ANA, "First Writer", CREATED, UPDATED),
        skills_rows=[(7, "Python")],
    )
    connection = _Connection(cursor)
    monkeypatch.setattr("app.sql_profile._connect", lambda: connection)

    result = PostgresProfileStore().upsert_with_skills(ANA, "Second Writer")

    assert result.profile.full_name == "First Writer"
    assert result.profile.created_at == CREATED
    assert result.profile.updated_at == UPDATED
    assert [(skill.skill_id, skill.name) for skill in result.skills] == [(7, "Python")]
    assert connection.commit_calls == 1
    assert connection.rollback_calls == 0
    insert_sql = cursor.statements[0][0]
    assert "ON CONFLICT (user_id) DO NOTHING" in insert_sql
    assert "EXCLUDED.full_name" not in insert_sql


def test_upsert_with_skills_rolls_back_when_response_read_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = _Cursor(
        inserted_row=(ANA, "Ana Lim", CREATED, CREATED),
        profile_row=None,
        fail_on_skills_read=True,
    )
    connection = _Connection(cursor)
    monkeypatch.setattr("app.sql_profile._connect", lambda: connection)

    with pytest.raises(SqlAccessError, match="profile could not be saved"):
        PostgresProfileStore().upsert_with_skills(ANA, "Ana Lim")

    assert connection.commit_calls == 0
    assert connection.rollback_calls == 1
    assert connection.closed
