"""Token verification tests.

These use a locally generated HS256 secret rather than a real Supabase project,
so they run offline. Synthetic values only; never put a real token in a test.
"""

import datetime as dt
from collections.abc import Iterator
from uuid import uuid4

import jwt
import pytest
from fastapi import Request

from app.auth import current_user
from app.config import Settings, get_settings
from app.errors import ApiError

SECRET = "test-secret-not-used-anywhere-real-32-bytes-minimum"


def make_request(token: str | None) -> Request:
    headers = [(b"authorization", f"Bearer {token}".encode())] if token else []
    return Request({"type": "http", "method": "GET", "path": "/api/me", "headers": headers})


def make_token(**overrides: object) -> str:
    now = dt.datetime.now(dt.UTC)
    claims: dict[str, object] = {
        "sub": str(uuid4()),
        "aud": "authenticated",
        "email": "student@example.edu",
        "iat": now,
        "exp": now + dt.timedelta(hours=1),
    }
    claims.update(overrides)
    return jwt.encode(claims, SECRET, algorithm="HS256")


def hs256_settings() -> Settings:
    return Settings(
        app_env="development",
        supabase_url="",
        supabase_jwt_secret=SECRET,
        allow_unverified_tokens=False,
    )


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_valid_token_identifies_the_student() -> None:
    subject = str(uuid4())
    user = current_user(make_request(make_token(sub=subject)), hs256_settings())
    assert str(user.user_id) == subject
    assert user.email == "student@example.edu"


def test_missing_header_is_rejected() -> None:
    with pytest.raises(ApiError) as caught:
        current_user(make_request(None), hs256_settings())
    assert caught.value.status_code == 401


def test_tampered_signature_is_rejected() -> None:
    token = make_token()
    forged = token[:-4] + ("aaaa" if not token.endswith("aaaa") else "bbbb")
    with pytest.raises(ApiError) as caught:
        current_user(make_request(forged), hs256_settings())
    assert caught.value.code == "unauthenticated"


def test_token_signed_with_another_secret_is_rejected() -> None:
    foreign = jwt.encode(
        {"sub": str(uuid4()), "aud": "authenticated"},
        "a-different-secret-also-long-enough-for-sha256",
        algorithm="HS256",
    )
    with pytest.raises(ApiError) as caught:
        current_user(make_request(foreign), hs256_settings())
    assert caught.value.code == "unauthenticated"


def test_expired_token_is_rejected() -> None:
    past = dt.datetime.now(dt.UTC) - dt.timedelta(hours=2)
    expired = make_token(iat=past, exp=past + dt.timedelta(minutes=1))
    with pytest.raises(ApiError) as caught:
        current_user(make_request(expired), hs256_settings())
    assert caught.value.status_code == 401


def test_wrong_audience_is_rejected() -> None:
    with pytest.raises(ApiError) as caught:
        current_user(make_request(make_token(aud="anon")), hs256_settings())
    assert caught.value.code == "unauthenticated"


def test_token_without_a_subject_is_rejected() -> None:
    token = jwt.encode({"aud": "authenticated"}, SECRET, algorithm="HS256")
    with pytest.raises(ApiError) as caught:
        current_user(make_request(token), hs256_settings())
    assert caught.value.status_code == 401


def test_unconfigured_api_reports_its_own_fault() -> None:
    """No verification material is a server problem, not a bad token."""
    blank = Settings(
        app_env="development",
        supabase_url="",
        supabase_jwt_secret="",
        allow_unverified_tokens=False,
    )
    with pytest.raises(ApiError) as caught:
        current_user(make_request(make_token()), blank)
    assert caught.value.status_code == 500


def test_development_bypass_skips_verification() -> None:
    permissive = Settings(
        app_env="development",
        supabase_url="",
        supabase_jwt_secret="",
        allow_unverified_tokens=True,
    )
    subject = str(uuid4())
    unsigned = jwt.encode(
        {"sub": subject, "aud": "authenticated"},
        "an-unrelated-signing-key-long-enough",
        algorithm="HS256",
    )
    user = current_user(make_request(unsigned), permissive)
    assert str(user.user_id) == subject


def test_bypass_is_refused_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_ALLOW_UNVERIFIED_TOKENS", "true")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError):
        get_settings()
