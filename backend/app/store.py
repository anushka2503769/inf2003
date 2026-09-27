"""Where profiles are kept.

`ProfileStore` is the seam for the database work. The in-memory implementation
below lets the sign-in and profile screens run end to end today; the PostgreSQL
implementation replaces it by satisfying the same three methods, and no route
handler changes.

The in-memory store is per process and is lost on restart. It is a development
stand-in, not a cache and not a fallback to keep in production.
"""

import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import Protocol
from uuid import UUID

from .config import get_settings
from .schemas import Profile, Skill

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class ProfileSnapshot:
    """The profile response data read from one store operation."""

    profile: Profile
    skills: list[Skill]


class ProfileStore(Protocol):
    def get(self, user_id: UUID) -> Profile | None:
        """Returns the profile, or None when the student has no row yet."""

    def upsert(self, user_id: UUID, full_name: str) -> Profile:
        """Creates the row, or returns the existing row unchanged."""

    def get_with_skills(self, user_id: UUID) -> ProfileSnapshot | None:
        """Reads a profile and its confirmed skills through this store."""

    def upsert_with_skills(self, user_id: UUID, full_name: str) -> ProfileSnapshot:
        """Creates or reads a profile and its skills as one store operation."""

    def update_name(self, user_id: UUID, full_name: str) -> Profile | None:
        """Renames an existing student. Returns None when there is no row."""


class InMemoryProfileStore:
    """Thread-safe dictionary store. Replace with the PostgreSQL implementation."""

    def __init__(self) -> None:
        self._rows: dict[UUID, Profile] = {}
        self._lock = threading.Lock()

    def get(self, user_id: UUID) -> Profile | None:
        with self._lock:
            return self._rows.get(user_id)

    def upsert(self, user_id: UUID, full_name: str) -> Profile:
        with self._lock:
            existing = self._rows.get(user_id)
            if existing is not None:
                return existing
            now = _now()
            profile = Profile(
                user_id=user_id,
                full_name=full_name,
                created_at=now,
                updated_at=now,
            )
            self._rows[user_id] = profile
            return profile

    def get_with_skills(self, user_id: UUID) -> ProfileSnapshot | None:
        with self._lock:
            profile = self._rows.get(user_id)
            return ProfileSnapshot(profile=profile, skills=[]) if profile else None

    def upsert_with_skills(self, user_id: UUID, full_name: str) -> ProfileSnapshot:
        with self._lock:
            existing = self._rows.get(user_id)
            if existing is None:
                now = _now()
                existing = Profile(
                    user_id=user_id,
                    full_name=full_name,
                    created_at=now,
                    updated_at=now,
                )
                self._rows[user_id] = existing
            return ProfileSnapshot(profile=existing, skills=[])

    def update_name(self, user_id: UUID, full_name: str) -> Profile | None:
        with self._lock:
            existing = self._rows.get(user_id)
            if existing is None:
                return None
            profile = existing.model_copy(update={"full_name": full_name, "updated_at": _now()})
            self._rows[user_id] = profile
            return profile

    def clear(self) -> None:
        """Test helper. Not part of the ProfileStore protocol."""
        with self._lock:
            self._rows.clear()


_memory_store = InMemoryProfileStore()


@lru_cache
def _select_store() -> ProfileStore:
    """PostgreSQL when it is configured, the development stand-in otherwise.

    A teammate without DATABASE_URL still gets a running app, which is what the
    in-memory store is for. A deployment silently keeping profiles in memory is
    not: it would lose every profile on restart while appearing to work, so
    production refuses to start instead.
    """
    settings = get_settings()
    if settings.database_url:
        from .sql_profile import PostgresProfileStore

        return PostgresProfileStore()

    if settings.is_production:
        raise RuntimeError("DATABASE_URL must be set when APP_ENV=production.")

    logger.warning(
        "DATABASE_URL is not set; profiles are kept in memory and lost on restart. "
        "Development only."
    )
    return _memory_store


def get_profile_store() -> ProfileStore:
    """FastAPI dependency. Override in tests or swap for the database store."""
    return _select_store()
