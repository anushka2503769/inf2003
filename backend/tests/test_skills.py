"""Skill dictionary and confirmed-skill routes, against a real database.

Skipped unless TEST_DATABASE_URL is set; see tests/test_sql_profile.py for why
that is deliberately not DATABASE_URL. These go through the HTTP routes rather
than the SQL functions, because the contract in docs/API.md is about status
codes, bodies and ordering as much as about rows.
"""

import asyncio
import os
from collections.abc import Iterator
from typing import Any
from uuid import UUID

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

# A small dictionary with deliberate awkward cases: mixed case that must sort
# together, and names holding LIKE wildcards that must stay literal.
DICTIONARY = ["Python", "PostgreSQL", "pytest", "SQL", "C_sharp", "100% Remote", "React"]


@pytest.fixture(autouse=True)
def database(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    from app import config

    config.get_settings.cache_clear()
    _seed()
    yield
    _reset()
    config.get_settings.cache_clear()


def _open() -> psycopg2.extensions.connection:
    return psycopg2.connect(TEST_DATABASE_URL)


def _reset() -> None:
    conn = _open()
    try:
        with conn.cursor() as cursor:
            cursor.execute("TRUNCATE public.users, public.skills CASCADE")
            cursor.execute("DELETE FROM auth.users")
        conn.commit()
    finally:
        conn.close()


def _seed() -> None:
    _reset()
    conn = _open()
    try:
        with conn.cursor() as cursor:
            for name in DICTIONARY:
                cursor.execute("INSERT INTO public.skills (name) VALUES (%s)", (name,))
        conn.commit()
    finally:
        conn.close()


def _sign_up(user_id: UUID, full_name: str) -> None:
    """Create the Supabase auth account and finish onboarding."""
    conn = _open()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO auth.users (id) VALUES (%s) ON CONFLICT DO NOTHING",
                (str(user_id),),
            )
            cursor.execute(
                "INSERT INTO public.users (user_id, full_name) VALUES (%s, %s)",
                (str(user_id), full_name),
            )
        conn.commit()
    finally:
        conn.close()


def _skill_id(name: str) -> int:
    """Resolve by canonical name, never by a hardcoded number."""
    conn = _open()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT skill_id FROM public.skills WHERE lower(name) = lower(%s)", (name,)
            )
            return cursor.fetchone()[0]
    finally:
        conn.close()


def _updated_at(user_id: UUID):
    conn = _open()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT updated_at FROM public.users WHERE user_id = %s", (str(user_id),)
            )
            return cursor.fetchone()[0]
    finally:
        conn.close()


def call(method: str, path: str, user_id: UUID | None = ANA) -> httpx.Response:
    from app.auth import AuthenticatedUser, current_user
    from app.main import app

    if user_id is None:
        app.dependency_overrides.pop(current_user, None)
    else:
        app.dependency_overrides[current_user] = lambda: AuthenticatedUser(
            user_id=user_id, email=f"{user_id}@example.edu"
        )

    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path)

    try:
        return asyncio.run(send())
    finally:
        app.dependency_overrides.pop(current_user, None)


def body(response: httpx.Response) -> Any:
    return response.json()


def test_search_requires_a_token() -> None:
    assert call("GET", "/api/skills", user_id=None).status_code == 401


def test_empty_query_lists_alphabetically_ignoring_case() -> None:
    response = call("GET", "/api/skills?limit=100")
    assert response.status_code == 200
    names = [item["name"] for item in body(response)["items"]]
    assert names == sorted(DICTIONARY, key=str.lower)
    assert body(response)["has_more"] is False


def test_search_is_case_insensitive_and_matches_anywhere() -> None:
    names = [item["name"] for item in body(call("GET", "/api/skills?q=SQL"))["items"]]
    assert names == ["PostgreSQL", "SQL"]


def test_percent_is_literal_not_a_wildcard() -> None:
    """A bare % would otherwise match the whole dictionary."""
    items = body(call("GET", "/api/skills?q=%25"))["items"]
    assert [item["name"] for item in items] == ["100% Remote"]


def test_underscore_is_literal_not_a_single_character_wildcard() -> None:
    items = body(call("GET", "/api/skills?q=C_"))["items"]
    assert [item["name"] for item in items] == ["C_sharp"]


def test_no_match_returns_an_empty_list() -> None:
    assert body(call("GET", "/api/skills?q=zzzznothing")) == {"items": [], "has_more": False}


def test_has_more_reports_results_beyond_the_limit() -> None:
    payload = body(call("GET", "/api/skills?limit=2"))
    assert len(payload["items"]) == 2
    assert payload["has_more"] is True


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "limit=abc", "q=" + "x" * 101])
def test_invalid_query_values_are_rejected(query: str) -> None:
    response = call("GET", f"/api/skills?{query}")
    assert response.status_code == 422
    assert body(response)["error"]["code"] == "validation_failed"


def test_unknown_query_parameter_is_rejected() -> None:
    """A typo must not quietly return unfiltered results."""
    response = call("GET", "/api/skills?limlt=5")
    assert response.status_code == 422
    assert "limlt" in body(response)["error"]["message"]


def test_search_works_before_onboarding() -> None:
    """The first-login screen searches before any profile row exists."""
    assert call("GET", "/api/skills?q=python").status_code == 200


def test_confirming_a_skill_returns_no_content_and_shows_up_on_the_profile() -> None:
    _sign_up(ANA, "Ana Lim")
    response = call("PUT", f"/api/me/skills/{_skill_id('Python')}")
    assert response.status_code == 204
    assert response.content == b""

    skills = body(call("GET", "/api/me"))["skills"]
    assert [skill["name"] for skill in skills] == ["Python"]


def test_confirmed_skills_are_ordered_by_name() -> None:
    _sign_up(ANA, "Ana Lim")
    for name in ("SQL", "Python", "pytest"):
        assert call("PUT", f"/api/me/skills/{_skill_id(name)}").status_code == 204

    names = [skill["name"] for skill in body(call("GET", "/api/me"))["skills"]]
    # Ordered by lower(name): "pytest" precedes "python" at the fourth letter,
    # and mixed case does not group separately from lowercase.
    assert names == ["pytest", "Python", "SQL"]


def test_confirming_twice_is_a_successful_no_op() -> None:
    _sign_up(ANA, "Ana Lim")
    skill_id = _skill_id("Python")
    assert call("PUT", f"/api/me/skills/{skill_id}").status_code == 204

    after_first = _updated_at(ANA)
    assert call("PUT", f"/api/me/skills/{skill_id}").status_code == 204

    assert len(body(call("GET", "/api/me"))["skills"]) == 1
    # docs/API.md: repeated no-ops preserve updated_at.
    assert _updated_at(ANA) == after_first


def test_a_membership_change_moves_updated_at() -> None:
    _sign_up(ANA, "Ana Lim")
    before = _updated_at(ANA)
    call("PUT", f"/api/me/skills/{_skill_id('Python')}")
    assert _updated_at(ANA) > before


def test_removing_a_skill_keeps_the_dictionary_entry() -> None:
    _sign_up(ANA, "Ana Lim")
    skill_id = _skill_id("Python")
    call("PUT", f"/api/me/skills/{skill_id}")

    assert call("DELETE", f"/api/me/skills/{skill_id}").status_code == 204
    assert body(call("GET", "/api/me"))["skills"] == []
    # The shared entry survives: another student can still confirm it.
    assert _skill_id("Python") == skill_id


def test_removing_twice_is_safe() -> None:
    _sign_up(ANA, "Ana Lim")
    skill_id = _skill_id("Python")
    call("PUT", f"/api/me/skills/{skill_id}")
    assert call("DELETE", f"/api/me/skills/{skill_id}").status_code == 204
    assert call("DELETE", f"/api/me/skills/{skill_id}").status_code == 204


def test_removing_an_unknown_skill_is_already_the_desired_state() -> None:
    _sign_up(ANA, "Ana Lim")
    assert call("DELETE", "/api/me/skills/987654").status_code == 204


def test_confirming_an_unknown_skill_is_not_found() -> None:
    _sign_up(ANA, "Ana Lim")
    response = call("PUT", "/api/me/skills/987654")
    assert response.status_code == 404
    assert body(response)["error"]["details"]["resource"] == "skill"


def test_membership_before_onboarding_is_not_found() -> None:
    for method in ("PUT", "DELETE"):
        response = call(method, f"/api/me/skills/{_skill_id('Python')}")
        assert response.status_code == 404
        assert body(response)["error"]["details"]["resource"] == "profile"


@pytest.mark.parametrize("skill_id", ["0", "-1", "abc", "2147483648"])
def test_invalid_path_ids_are_rejected(skill_id: str) -> None:
    _sign_up(ANA, "Ana Lim")
    response = call("PUT", f"/api/me/skills/{skill_id}")
    assert response.status_code == 422
    assert body(response)["error"]["code"] == "validation_failed"


def test_one_student_cannot_change_another_students_skills() -> None:
    _sign_up(ANA, "Ana Lim")
    _sign_up(BEN, "Ben Ong")
    skill_id = _skill_id("Python")

    assert call("PUT", f"/api/me/skills/{skill_id}", user_id=BEN).status_code == 204

    assert body(call("GET", "/api/me", user_id=ANA))["skills"] == []
    assert len(body(call("GET", "/api/me", user_id=BEN))["skills"]) == 1

    # Ana removing "her" copy must not touch Ben's row.
    assert call("DELETE", f"/api/me/skills/{skill_id}", user_id=ANA).status_code == 204
    assert len(body(call("GET", "/api/me", user_id=BEN))["skills"]) == 1
