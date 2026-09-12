"""Where profiles are kept.

`ProfileStore` is the seam for the database work. The in-memory implementation
below lets the sign-in and profile screens run end to end today; the PostgreSQL
implementation replaces it by satisfying the same three methods, and no route
handler changes.

The in-memory store is per process and is lost on restart. It is a development
stand-in, not a cache and not a fallback to keep in production.
"""

import threading
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from .schemas import Profile


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


_store: ProfileStore = InMemoryProfileStore()


def get_profile_store() -> ProfileStore:
    """FastAPI dependency. Override in tests or swap for the database store."""
    return _store
