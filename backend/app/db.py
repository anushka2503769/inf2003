"""
Shared MongoDB connection for the FastAPI app.
Import `get_db()` wherever a router needs database access.
"""

import os

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database

load_dotenv()

_uri = os.getenv("MONGODB_URI")
if not _uri:
    raise RuntimeError("MONGODB_URI is not set. Check your .env file.")

_client: MongoClient = MongoClient(_uri)
_db: Database = _client["jobless_simulator"]  # change if your DB name differs


def get_db() -> Database:
    """FastAPI dependency: yields the shared database handle."""
    return _db