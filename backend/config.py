"""Runtime configuration.

Values come from the process environment, which `uv run` populates from
backend/.env when that file exists. Nothing here is sent to the browser.
"""

import os
from dataclasses import dataclass
from functools import lru_cache


def _flag(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_env: str
    supabase_url: str
    supabase_jwt_secret: str
    allow_unverified_tokens: bool

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def jwks_url(self) -> str:
        """Where Supabase publishes the public keys for asymmetric tokens."""
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    @property
    def has_verification_material(self) -> bool:
        return bool(self.supabase_url) or bool(self.supabase_jwt_secret)


@lru_cache
def get_settings() -> Settings:
    settings = Settings(
        app_env=os.environ.get("APP_ENV", "development"),
        supabase_url=os.environ.get("SUPABASE_URL", "").strip(),
        supabase_jwt_secret=os.environ.get("SUPABASE_JWT_SECRET", "").strip(),
        allow_unverified_tokens=_flag("AUTH_ALLOW_UNVERIFIED_TOKENS"),
    )

    # The development escape hatch must never survive a deployment. Failing at
    # import time is better than serving traffic that trusts any token.
    if settings.is_production and settings.allow_unverified_tokens:
        raise RuntimeError("AUTH_ALLOW_UNVERIFIED_TOKENS must not be set when APP_ENV=production.")

    return settings
