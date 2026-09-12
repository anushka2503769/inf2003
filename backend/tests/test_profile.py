"""Profile route tests.

Authentication is exercised through a fake token verifier rather than a real
Supabase project, so these run offline and without credentials. The token
verification logic itself is covered in test_auth.py.
"""

import asyncio
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

from app.auth import AuthenticatedUser, current_user
from app.main import app
from app.store import InMemoryProfileStore, get_profile_store

ANA = UUID("11111111-1111-4111-8111-111111111111")
BEN = UUID("22222222-2222-4222-8222-222222222222")


@pytest.fixture
def store() -> Iterator[InMemoryProfileStore]:
    """A clean store per test, so one test cannot see another's rows."""
    fresh = InMemoryProfileStore()
    app.dependency_overrides[get_profile_store] = lambda: fresh
    yield fresh
    app.dependency_overrides.pop(get_profile_store, None)


def sign_in_as(user_id: UUID) -> None:
    app.dependency_overrides[current_user] = lambda: AuthenticatedUser(
        user_id=user_id, email=f"{user_id}@example.edu"
    )


def sign_out() -> None:
    app.dependency_overrides.pop(current_user, None)


def call(method: str, path: str, json: Any = None) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, json=json)

    return asyncio.run(send())


# --------------------------------------------------------------------------- #
# Reading                                                                      #
# --------------------------------------------------------------------------- #


def test_me_requires_a_token(store: InMemoryProfileStore) -> None:
    sign_out()
    response = call("GET", "/api/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_me_reports_not_found_before_onboarding(store: InMemoryProfileStore) -> None:
    sign_in_as(ANA)
    response = call("GET", "/api/me")
    assert response.status_code == 404
    # The browser routes to onboarding on this exact code.
    assert response.json()["error"]["code"] == "not_found"
    sign_out()


# --------------------------------------------------------------------------- #
# Onboarding                                                                   #
# --------------------------------------------------------------------------- #


def test_onboarding_creates_the_profile(store: InMemoryProfileStore) -> None:
    sign_in_as(ANA)
    created = call("POST", "/api/me", {"full_name": "Ana Lim"})
    assert created.status_code == 200
    body = created.json()
    assert body["profile"]["full_name"] == "Ana Lim"
    assert body["profile"]["user_id"] == str(ANA)
    assert body["onboarding_complete"] is True

    fetched = call("GET", "/api/me")
    assert fetched.status_code == 200
    assert fetched.json()["profile"]["full_name"] == "Ana Lim"
    sign_out()


def test_onboarding_is_safe_to_retry(store: InMemoryProfileStore) -> None:
    """A retry after a timeout must not fail with a conflict."""
    sign_in_as(ANA)
    first = call("POST", "/api/me", {"full_name": "Ana Lim"})
    second = call("POST", "/api/me", {"full_name": "Ana Lim"})
    assert second.status_code == 200
    assert second.json()["profile"]["created_at"] == first.json()["profile"]["created_at"]
    sign_out()


def test_name_whitespace_is_normalised(store: InMemoryProfileStore) -> None:
    sign_in_as(ANA)
    response = call("POST", "/api/me", {"full_name": "  Ana   Lim  "})
    assert response.json()["profile"]["full_name"] == "Ana Lim"
    sign_out()


@pytest.mark.parametrize("name", ["", "   ", "A" * 81, "Ana\u0007Lim"])
def test_invalid_names_are_rejected(store: InMemoryProfileStore, name: str) -> None:
    sign_in_as(ANA)
    response = call("POST", "/api/me", {"full_name": name})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"
    sign_out()


# --------------------------------------------------------------------------- #
# Name editing                                                                 #
# --------------------------------------------------------------------------- #


def test_name_can_be_changed(store: InMemoryProfileStore) -> None:
    sign_in_as(ANA)
    call("POST", "/api/me", {"full_name": "Ana Lim"})
    response = call("PATCH", "/api/me", {"full_name": "Ana Lim-Tan"})
    assert response.status_code == 200
    assert response.json()["full_name"] == "Ana Lim-Tan"
    assert call("GET", "/api/me").json()["profile"]["full_name"] == "Ana Lim-Tan"
    sign_out()


def test_editing_updates_the_timestamp(store: InMemoryProfileStore) -> None:
    """updated_at is maintained by the write, not by a column default."""
    sign_in_as(ANA)
    created = call("POST", "/api/me", {"full_name": "Ana Lim"}).json()["profile"]
    edited = call("PATCH", "/api/me", {"full_name": "Ana Tan"}).json()
    assert edited["updated_at"] >= created["updated_at"]
    assert edited["created_at"] == created["created_at"]
    sign_out()


def test_empty_patch_is_rejected(store: InMemoryProfileStore) -> None:
    sign_in_as(ANA)
    call("POST", "/api/me", {"full_name": "Ana Lim"})
    response = call("PATCH", "/api/me", {})
    assert response.status_code == 422
    sign_out()


def test_editing_before_onboarding_is_not_found(store: InMemoryProfileStore) -> None:
    sign_in_as(ANA)
    response = call("PATCH", "/api/me", {"full_name": "Ana Lim"})
    assert response.status_code == 404
    sign_out()


# --------------------------------------------------------------------------- #
# Isolation                                                                    #
# --------------------------------------------------------------------------- #


def test_students_cannot_see_or_edit_each_other(store: InMemoryProfileStore) -> None:
    sign_in_as(ANA)
    call("POST", "/api/me", {"full_name": "Ana Lim"})
    sign_out()

    sign_in_as(BEN)
    assert call("GET", "/api/me").status_code == 404
    call("POST", "/api/me", {"full_name": "Ben Ong"})
    assert call("GET", "/api/me").json()["profile"]["full_name"] == "Ben Ong"
    call("PATCH", "/api/me", {"full_name": "Ben O."})
    sign_out()

    sign_in_as(ANA)
    assert call("GET", "/api/me").json()["profile"]["full_name"] == "Ana Lim"
    sign_out()


def test_user_id_in_the_body_is_ignored(store: InMemoryProfileStore) -> None:
    """The row is keyed on the token subject, never on client-supplied input."""
    sign_in_as(ANA)
    response = call("POST", "/api/me", {"full_name": "Ana Lim", "user_id": str(uuid4())})
    assert response.json()["profile"]["user_id"] == str(ANA)
    sign_out()
