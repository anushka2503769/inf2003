"""Load jobs into SQL and MongoDB from the command line (WP-5).

Runs the same pipeline as POST /api/jobs/external/fetch-multi, prints the summary
as JSON and exits non-zero on total failure.

    cd backend
    # keyless provider APIs
    uv run --env-file .env python scripts/ingest_jobs.py \
        --sources arbeitnow ai_dev_jobs --limit-per-source 200
    # the LinkedIn export written by scripts/fetch_linkedin_apify.py (no network call)
    uv run --env-file .env python scripts/ingest_jobs.py --file ../data/raw/linkedin_sg_<date>.json

Configuration (DATABASE_URL, MONGODB_URI, MONGODB_DATABASE) comes from the process
environment, which `--env-file .env` fills; this script never reads .env itself.

Exit codes: 0 when at least one job was inserted or updated (or nothing failed),
1 on total failure. Total failure means nothing was inserted or updated and there was
at least one error (or no jobs were found at all), or an unrecoverable exception such
as an unreachable database, an unreadable file or an unavailable provider.
"""

import argparse
import json
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.errors import ApiError  # noqa: E402
from app.job_sources import (  # noqa: E402
    SOURCE_REGISTRY,
    ProviderJobError,
    collect_provider_jobs,
    load_linkedin_apify_file,
)
from app.jobs_external_multi import FetchSummary, ingest_provider_jobs  # noqa: E402
from app.sql_access import SqlAccessError  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest jobs into SQL and MongoDB.")
    where = parser.add_mutually_exclusive_group()
    where.add_argument(
        "--sources",
        nargs="+",
        metavar="SOURCE",
        help=f"Provider APIs to fetch (known: {', '.join(SOURCE_REGISTRY)}). Default: arbeitnow.",
    )
    where.add_argument(
        "--file",
        type=Path,
        help="LinkedIn Apify export (source linkedin_apify); makes no network call.",
    )
    parser.add_argument(
        "--limit-per-source",
        type=int,
        default=50,
        help="Maximum jobs per provider (default 50; ignored with --file).",
    )
    args = parser.parse_args(argv)
    if args.limit_per_source < 1:
        parser.error("--limit-per-source must be at least 1")
    if args.file is None and not args.sources:
        args.sources = ["arbeitnow"]
    return args


@contextmanager
def open_stores() -> Iterator[object]:
    """Hold the job pipeline lock and yield the MongoDB database, as the admin route does."""
    from app.db import get_db
    from app.sql_access import job_pipeline_lock

    with job_pipeline_lock():
        yield get_db()


def is_total_failure(summary: FetchSummary) -> bool:
    nothing_stored = summary.inserted + summary.updated == 0
    return nothing_stored and (bool(summary.errors) or summary.requested == 0)


def run(
    args: argparse.Namespace,
    *,
    collect: Callable[..., tuple[list[dict], list[str]]] = collect_provider_jobs,
    load_file: Callable[..., tuple[list[dict], list[str]]] = load_linkedin_apify_file,
    stores: Callable[[], Any] = open_stores,
    out: Callable[[str], None] = print,
) -> int:
    """Run the pipeline, print the summary and return the process exit code."""
    try:
        if args.file is not None:
            jobs, rejected = load_file(args.file)
        else:
            jobs, rejected = collect(args.sources, limit_per_source=args.limit_per_source)
        with stores() as db:
            _, summary = ingest_provider_jobs(db, jobs, rejected)
    except Exception as exc:
        # Only our own errors are echoed; driver errors can name hosts, so show the type.
        known = isinstance(exc, (ProviderJobError, ApiError, SqlAccessError, RuntimeError))
        message = str(exc) if known and str(exc) else type(exc).__name__
        out(f"Ingestion failed: {message}"[:300])
        return 1

    if summary.requested == 0 and not summary.errors:
        summary.errors.append("No jobs were found in the input.")
    out(json.dumps(summary.model_dump(), indent=2))
    return 1 if is_total_failure(summary) else 0


def main(argv: list[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
