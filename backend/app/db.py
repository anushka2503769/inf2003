"""
Shared MongoDB connection for the FastAPI app.
Import `get_db()` wherever a router needs database access.
"""

from pymongo import MongoClient
from pymongo.database import Database

from .config import get_settings
from .errors import ApiError

_client: MongoClient | None = None
_db: Database | None = None


def get_db() -> Database:
    """Return a shared database handle, creating it only when a route needs it."""
    global _client, _db
    settings = get_settings()
    if not settings.mongodb_uri:
        raise ApiError(
            503,
            "service_unavailable",
            "Document storage is not configured.",
        )
    if _db is None:
        _client = MongoClient(settings.mongodb_uri)
        _db = _client[settings.mongodb_database]
    return _db


def reset_client_for_tests() -> None:
    """Close the lazy client so isolated tests can configure a new URI."""
    global _client, _db
    if _client is not None:
        _client.close()
    _client = None
    _db = None
