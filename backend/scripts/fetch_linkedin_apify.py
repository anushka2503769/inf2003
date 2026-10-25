"""Fetch Singapore job postings from LinkedIn through an Apify actor.

Runs `curious_coder/linkedin-jobs-scraper` once per search keyword, keeps only the
fields the job pipeline needs, drops recruiter personal data, removes duplicates by
LinkedIn job id and writes one JSON file under data/raw/. Importing that file into
SQL and MongoDB is a separate step (PRD WP-5).

The Apify token is read from APIFY_TOKEN (put it in backend/.env, never commit it).
Spending is capped with Apify's own maxTotalChargeUsd per run plus a total budget.

    cd backend
    uv run --env-file .env python scripts/fetch_linkedin_apify.py --dry-run
    uv run --env-file .env python scripts/fetch_linkedin_apify.py --sample 5
    uv run --env-file .env python scripts/fetch_linkedin_apify.py
"""

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

ACTOR_ID = "hKByXkMQaC5Qt9UMN"  # curious_coder/linkedin-jobs-scraper
ACTOR_NAME = "curious_coder/linkedin-jobs-scraper"
API_BASE = "https://api.apify.com/v2"
# Free-plan price per result in October 2026 (paid plans: 0.001). Used as a floor for
# the budget, because a run's usageTotalUsd may not include the actor's event charges.
PRICE_PER_ITEM_USD = 0.002
REPO_ROOT = Path(__file__).resolve().parents[2]

# Spread across role families so the skill-gap screen has several roles to compare.
DEFAULT_KEYWORDS = [
    "software engineer intern",
    "junior software engineer",
    "frontend developer intern",
    "backend developer intern",
    "data analyst intern",
    "data science intern",
    "machine learning intern",
    "cybersecurity intern",
    "devops cloud intern",
    "business analyst intern",
    "financial analyst intern",
    "product manager intern",
    "ui ux designer intern",
]

# Allowlist of actor output fields. Recruiter names/photos/profiles, logos and
# applicant counts are deliberately dropped.
KEPT_FIELDS = (
    "id",
    "title",
    "companyName",
    "location",
    "postedAt",
    "employmentType",
    "seniorityLevel",
    "jobFunction",
    "industries",
    "applyUrl",
    "descriptionText",
    "descriptionHtml",
)
REQUIRED_FIELDS = ("id", "title", "companyName", "descriptionText")

TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--keyword",
        action="append",
        dest="keywords",
        help="Search keyword; repeat for several. Defaults to a built-in role list.",
    )
    parser.add_argument("--location", default="Singapore")
    parser.add_argument("--limit-per-search", type=int, default=50)
    parser.add_argument(
        "--date-posted",
        default="pastMonth",
        choices=["anyTime", "past24Hours", "pastWeek", "pastMonth"],
    )
    parser.add_argument(
        "--max-charge-usd",
        type=float,
        default=2.0,
        help="Total spending cap across all runs (default 2.0).",
    )
    parser.add_argument(
        "--sample",
        type=int,
        metavar="N",
        help="Run only the first keyword with N results, to check the output shape.",
    )
    parser.add_argument("--out", type=Path, help="Output file (default data/raw/...).")
    parser.add_argument("--force", action="store_true", help="Overwrite the output file.")
    parser.add_argument("--dry-run", action="store_true", help="Print the planned runs and exit.")
    parser.add_argument("--timeout-secs", type=int, default=900, help="Per run.")
    return parser.parse_args()


def actor_input(keyword: str, args: argparse.Namespace, limit: int) -> dict[str, Any]:
    return {
        "keywords": keyword,
        "location": args.location,
        "datePosted": args.date_posted,
        "limitPerSource": limit,
        "scrapeCompany": False,
        "urls": [],
    }


def start_run(
    session: requests.Session, payload: dict[str, Any], limit: int, cap: float
) -> dict[str, Any]:
    response = session.post(
        f"{API_BASE}/acts/{ACTOR_ID}/runs",
        params={"maxItems": limit, "maxTotalChargeUsd": f"{cap:.2f}"},
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["data"]


def wait_for_run(session: requests.Session, run_id: str, timeout_secs: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_secs
    while True:
        response = session.get(
            f"{API_BASE}/actor-runs/{run_id}", params={"waitForFinish": 60}, timeout=90
        )
        response.raise_for_status()
        run = response.json()["data"]
        if run["status"] in TERMINAL_STATUSES:
            return run
        if time.monotonic() > deadline:
            session.post(f"{API_BASE}/actor-runs/{run_id}/abort", timeout=30)
            raise TimeoutError(f"Run {run_id} exceeded {timeout_secs}s and was aborted.")


def dataset_items(session: requests.Session, dataset_id: str) -> list[dict[str, Any]]:
    response = session.get(
        f"{API_BASE}/datasets/{dataset_id}/items",
        params={"clean": "true", "format": "json"},
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def clean_job(item: dict[str, Any], keyword: str) -> dict[str, Any] | None:
    """Keep allowlisted fields; None when a field the pipeline needs is missing."""
    job = {field: item.get(field) for field in KEPT_FIELDS}
    job["id"] = str(job["id"]).strip() if job["id"] is not None else ""
    if any(not (isinstance(job[f], str) and job[f].strip()) for f in REQUIRED_FIELDS):
        return None
    # A canonical URL without tracking parameters doubles as the application URL,
    # because the public scraper usually returns an empty applyUrl.
    job["url"] = f"https://www.linkedin.com/jobs/view/{job['id']}/"
    job["search_keywords"] = [keyword]
    return job


def main() -> int:
    args = parse_args()
    keywords = args.keywords or DEFAULT_KEYWORDS
    limit = args.limit_per_search
    if args.sample:
        keywords, limit = keywords[:1], args.sample

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    suffix = "_sample" if args.sample else ""
    out = args.out or REPO_ROOT / "data" / "raw" / f"linkedin_sg_{today}{suffix}.json"

    print(f"Actor {ACTOR_NAME}; location {args.location!r}; posted {args.date_posted}")
    print(f"{len(keywords)} searches x up to {limit} jobs; budget ${args.max_charge_usd:.2f}")
    for keyword in keywords:
        print(f"  - {keyword}")
    print(f"Output: {out}")
    if args.dry_run:
        return 0

    token = os.environ.get("APIFY_TOKEN", "").strip()
    if not token:
        print("APIFY_TOKEN is not set. Add it to backend/.env and run with --env-file .env.")
        return 2
    if out.exists() and not args.force:
        print(f"{out} already exists; pass --force to overwrite.")
        return 2

    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token}"

    jobs: dict[str, dict[str, Any]] = {}
    searches: list[dict[str, Any]] = []
    spent = 0.0
    for keyword in keywords:
        remaining = args.max_charge_usd - spent
        if remaining < 0.05:
            print(f"Budget reached (${spent:.2f}); skipping the remaining searches.")
            break
        run = start_run(session, actor_input(keyword, args, limit), limit, remaining)
        run = wait_for_run(session, run["id"], args.timeout_secs)
        items = dataset_items(session, run["defaultDatasetId"])
        cost = max(float(run.get("usageTotalUsd") or 0.0), len(items) * PRICE_PER_ITEM_USD)
        spent += cost

        kept = new = 0
        for item in items:
            job = clean_job(item, keyword)
            if job is None:
                continue
            kept += 1
            existing = jobs.get(job["id"])
            if existing:
                existing["search_keywords"].append(keyword)
            else:
                jobs[job["id"]] = job
                new += 1
        searches.append(
            {
                "keyword": keyword,
                "run_id": run["id"],
                "status": run["status"],
                "returned": len(items),
                "kept": kept,
                "new": new,
                "usage_usd": round(cost, 4),
            }
        )
        print(
            f"{keyword!r}: {run['status']}, {len(items)} returned, {kept} usable, "
            f"{new} new, ${cost:.3f} (total ${spent:.3f})"
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "source": "linkedin_apify",
        "actor": ACTOR_NAME,
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "location": args.location,
        "date_posted": args.date_posted,
        "searches": searches,
        "job_count": len(jobs),
        "jobs": list(jobs.values()),
    }
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(jobs)} unique jobs to {out} (spent ${spent:.3f}).")
    return 0 if jobs else 1


if __name__ == "__main__":
    sys.exit(main())
