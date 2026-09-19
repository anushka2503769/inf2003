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
from datetime import UTC, datetime
from functools import lru_cache
from typing import Protocol
from uuid import UUID

from .config import get_settings
from .schemas import Profile

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


class ProfileStore(Protocol):
    def get(self, user_id: UUID) -> Profile | None:
        """Returns the profile, or None when the student has no row yet."""

    def upsert(self, user_id: UUID, full_name: str) -> Profile:
        """Creates the row, or updates the name if it already exists."""

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
            now = _now()
            profile = Profile(
                user_id=user_id,
                full_name=full_name,
                created_at=existing.created_at if existing else now,
                # updated_at is set by this write. A column default would only
                # ever record the insert (see docs/erd.md).
                updated_at=now,
            )
            self._rows[user_id] = profile
            return profile

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
