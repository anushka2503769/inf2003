"""
Shared Postgres (Supabase) connection for raw SQL reporting queries.
Reuses the same DATABASE_URL env var as skills_repository.py.
"""

import os

import psycopg2
from dotenv import load_dotenv
from psycopg2.extensions import connection as PGConnection

load_dotenv()

_DATABASE_URL = os.getenv("DATABASE_URL")


def get_pg_connection() -> PGConnection:
    """Opens a fresh Postgres connection. Caller is responsible for closing it."""
    if not _DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set. Check your .env file.")
    return psycopg2.connect(_DATABASE_URL)