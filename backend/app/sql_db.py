"""
Shared Postgres (Supabase) connection for raw SQL reporting queries.
Reuses the same DATABASE_URL env var as skills_repository.py.
"""

import psycopg2
from psycopg2.extensions import connection as PGConnection

from .config import get_settings


def get_pg_connection() -> PGConnection:
    """Opens a fresh Postgres connection. Caller is responsible for closing it."""
    database_url = get_settings().database_url
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Configure the backend before using SQL routes."
        )
    return psycopg2.connect(database_url)
