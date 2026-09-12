"""Authentication.

The browser signs in with Google through Supabase and sends the resulting
access token as `Authorization: Bearer <token>`. This module turns that token
into a trusted user id. It is the only place the backend decides who someone is,
so every protected route depends on `current_user`.

Three verification modes, chosen by configuration:

1. SUPABASE_URL set — verify the signature against the project's published JWKS.
   This is the normal path and works with Supabase asymmetric signing keys.
2. SUPABASE_JWT_SECRET set — verify with the legacy shared HS256 secret.
3. AUTH_ALLOW_UNVERIFIED_TOKENS=true — read the claims without checking the
   signature. Local development only; app.config refuses to start in production.
"""

import logging
from typing import Annotated, Any
from uuid import UUID

import jwt
from fastapi import Depends, Request
from jwt import PyJWKClient
from pydantic import BaseModel

from .config import Settings, get_settings
from .errors import ApiError

logger = logging.getLogger(__name__)

# Supabase issues access tokens with this audience for signed-in end users.
_AUDIENCE = "authenticated"

_jwk_client: PyJWKClient | None = None


class AuthenticatedUser(BaseModel):
    """The identity proven by the bearer token."""

    user_id: UUID
    email: str | None = None


def _unauthenticated(message: str) -> ApiError:
    return ApiError(401, "unauthenticated", message)


def _bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _unauthenticated("Sign in to continue.")
    return token.strip()


def _get_jwk_client(settings: Settings) -> PyJWKClient:
    """Cached across requests so the JWKS is fetched once, not per request."""
    global _jwk_client
    if _jwk_client is None:
        _jwk_client = PyJWKClient(settings.jwks_url, cache_keys=True, lifespan=3600)
    return _jwk_client


def _decode(token: str, settings: Settings) -> dict[str, Any]:
    if settings.allow_unverified_tokens:
        logger.warning("Accepting an unverified token; development configuration only.")
        return jwt.decode(token, options={"verify_signature": False, "verify_aud": False})

    if settings.supabase_url:
        signing_key = _get_jwk_client(settings).get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience=_AUDIENCE,
        )

    if settings.supabase_jwt_secret:
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience=_AUDIENCE,
        )

    # Misconfiguration, not a client mistake: say so instead of blaming the token.
    raise ApiError(
        500,
        "internal_error",
        "The API has no way to verify sign-in tokens. Set SUPABASE_URL in backend/.env.",
    )


def current_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthenticatedUser:
    """FastAPI dependency returning the signed-in student."""
    token = _bearer_token(request)

    try:
        claims = _decode(token, settings)
    except ApiError:
        raise
    except jwt.ExpiredSignatureError as exc:
        raise _unauthenticated("Your session has expired. Sign in again.") from exc
    except jwt.InvalidTokenError as exc:
        raise _unauthenticated("Your sign-in could not be verified.") from exc
    except Exception as exc:  # network failure reaching the JWKS endpoint
        logger.exception("Token verification failed unexpectedly.")
        raise ApiError(
            503, "internal_error", "Sign-in cannot be checked right now. Try again shortly."
        ) from exc

    subject = claims.get("sub")
    if not subject:
        raise _unauthenticated("Your sign-in could not be verified.")

    try:
        user_id = UUID(str(subject))
    except ValueError as exc:
        raise _unauthenticated("Your sign-in could not be verified.") from exc

    email = claims.get("email")
    return AuthenticatedUser(user_id=user_id, email=email if isinstance(email, str) else None)


CurrentUser = Annotated[AuthenticatedUser, Depends(current_user)]
