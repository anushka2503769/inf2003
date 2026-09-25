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


def main() -> None:
    """Create the title index when this helper is run as a script."""
    backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, backend_root)

    from app.db import get_db
    from app.jobs_search import ensure_title_indexes

    ensure_title_indexes(get_db())
    print("Indexes created (or already existed) on job_documents.title")


if __name__ == "__main__":
    main()
