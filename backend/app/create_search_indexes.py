"""
One-off script: creates the indexes the job title search endpoint needs.
Run this once (safe to re-run - MongoDB no-ops if the index already exists).

This version lives inside backend/app/, so it needs to climb up two
directory levels (app -> backend -> repo root) to find the repo root,
where Python can resolve 'backend' as a package.

Usage (from anywhere - repo root or backend/):
    uv run python backend/app/create_search_indexes.py
"""

import os
import sys

# app/ -> backend/ -> repo root (three levels up from this file itself)
repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, repo_root)

from backend.app.db import get_db  # NOTE: .db, not just "backend.app"
from backend.app.jobs_search import ensure_title_indexes

db = get_db()
ensure_title_indexes(db)
print("Indexes created (or already existed) on job_documents.title")