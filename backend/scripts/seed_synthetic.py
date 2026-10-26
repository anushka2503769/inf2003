"""Fill a DISPOSABLE PostgreSQL + MongoDB pair with synthetic data for the WP-10 benchmark.

    cd backend
    uv run --no-env-file python scripts/seed_synthetic.py \
        --database-url postgresql://postgres:postgres@127.0.0.1:5432/postgres \
        --mongodb-uri mongodb://127.0.0.1:27017/ --mongodb-database jobless_simulator_bench

The script refuses to run unless every URL points at 127.0.0.1 or localhost, and it
TRUNCATES the application tables and empties ``job_documents`` first. It needs migrations
001, 002 (the skill dictionary) and 003 applied, and the Mongo collections script loaded.
``scripts/run_benchmark.sh`` builds such a pair in throwaway Docker containers.

Shape (docs/PRD.md WP-10): N jobs (default 5,000), 3-12 requirements per job drawn from the
002 dictionary with a skewed popularity, 50 users with 5-20 skills and 0-50 tracker rows,
and one Mongo ``job_documents`` document per job. A fixed random seed makes the data
identical on every run. Optionally one extra "heavy" user with many tracker rows, used only
by the supplementary tracker-index variant.
"""

import argparse
import random
import sys
import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost"})
DEFAULT_JOBS = 5_000
DEFAULT_SEED = 20261026
USER_COUNT = 50
REQUIREMENTS_MIN, REQUIREMENTS_MAX = 3, 12
USER_SKILLS_MIN, USER_SKILLS_MAX = 5, 20
TRACKER_ROWS_MIN, TRACKER_ROWS_MAX = 0, 50
BASE_TIME = datetime(2026, 10, 1, tzinfo=timezone.utc)

# (value, weight). Skewed so a filter can be selective (INTERNSHIP + REMOTE is about 4%).
JOB_TYPES = [("FULL_TIME", 70), ("PART_TIME", 10), ("INTERNSHIP", 20)]
WORK_ARRANGEMENTS = [("ONSITE", 50), ("HYBRID", 30), ("REMOTE", 20)]
LOCATIONS = ["Singapore", "Remote", "Kuala Lumpur", "Jakarta", "Bangkok", "Hong Kong", "Sydney"]
ROLES = [
    ("Software Engineering", 30),
    ("Data Analytics", 20),
    ("Data Science", 12),
    ("Cybersecurity", 10),
    ("Product Management", 8),
    ("DevOps", 8),
    ("Design", 8),
    ("Quantum Computing", 1),  # deliberately rare: about 1% of jobs
]
STATUSES = ["NOT_INTERESTED", "SAVED", "APPLIED", "INTERVIEW", "REJECTED", "OFFER"]
INACTIVE_FRACTION = 0.05


class NotLocalError(RuntimeError):
    """A database URL points somewhere other than this machine."""


def url_host(url: str) -> str:
    """The host part of a postgresql:// or mongodb:// URL ('' when there is none)."""
    return (urlparse(url).hostname or "").lower()


def assert_local_urls(*urls: str) -> None:
    """Raise unless every URL names 127.0.0.1 or localhost explicitly.

    Anything else (a hostname, an Atlas SRV address, an unset/blank URL) is refused, so
    the seed can never TRUNCATE a shared database by a pasted connection string.
    """
    for url in urls:
        host = url_host(url)
        if host not in LOCAL_HOSTS:
            shown = host or "no host"
            raise NotLocalError(
                f"Refusing to run: database host is {shown!r}; only 127.0.0.1 or localhost "
                "are allowed (disposable local databases only)."
            )


def weighted_choice(rng: random.Random, options: Sequence[tuple[str, int]]) -> str:
    return rng.choices([v for v, _ in options], weights=[w for _, w in options], k=1)[0]


def skill_weights(count: int) -> list[float]:
    """Zipf-like popularity: a few skills appear in most postings, a long tail in few."""
    return [1.0 / (rank + 1) ** 0.8 for rank in range(count)]


def job_id_for(index: int) -> str:
    return str(uuid.UUID(int=(0x20261026 << 96) | index, version=4))


def user_id_for(index: int) -> str:
    return str(uuid.UUID(int=(0x20261027 << 96) | index, version=4))


def build_dataset(
    n_jobs: int, skill_ids: Sequence[int], seed: int = DEFAULT_SEED, heavy_rows: int = 0
) -> dict:
    """All rows as plain Python values. Pure and deterministic for a given argument tuple."""
    if n_jobs < 1:
        raise ValueError("n_jobs must be at least 1.")
    if len(skill_ids) < REQUIREMENTS_MAX:
        raise ValueError(f"Need at least {REQUIREMENTS_MAX} dictionary skills.")
    rng = random.Random(seed)
    weights = skill_weights(len(skill_ids))

    def draw_skills(k: int) -> list[int]:
        chosen: list[int] = []
        while len(chosen) < k:
            skill = rng.choices(skill_ids, weights=weights, k=1)[0]
            if skill not in chosen:
                chosen.append(skill)
        return chosen

    jobs, job_skills, documents = [], [], []
    for i in range(n_jobs):
        job_id = job_id_for(i)
        posted = BASE_TIME - timedelta(minutes=rng.randint(0, 60 * 24 * 90))
        role = weighted_choice(rng, ROLES)
        jobs.append(
            {
                "job_id": job_id,
                "source": "synthetic",
                "external_job_id": f"syn-{i}",
                "title": f"{role} {rng.choice(['Intern', 'Associate', 'Engineer', 'Lead'])} {i}",
                "company_name": f"Company {rng.randint(1, 400)}",
                "location": rng.choice(LOCATIONS),
                "job_type": weighted_choice(rng, JOB_TYPES),
                "work_arrangement": weighted_choice(rng, WORK_ARRANGEMENTS),
                "application_url": f"https://example.invalid/jobs/{i}",
                "source_posted_at": posted,
                "is_active": rng.random() >= INACTIVE_FRACTION,
            }
        )
        requirements = []
        for skill in draw_skills(rng.randint(REQUIREMENTS_MIN, REQUIREMENTS_MAX)):
            kind = "REQUIRED" if rng.random() < 0.6 else "PREFERRED"
            years = rng.choice([None, None, 1, 2, 3, 5])
            job_skills.append((job_id, skill, kind))
            requirements.append(
                {
                    "skill_id": skill,
                    "requirement_type": kind,
                    "minimum_years": years,
                    "evidence": f"Synthetic evidence for skill {skill}.",
                }
            )
        documents.append(
            {
                "job_id": job_id,
                "raw_jd": f"Synthetic job description {i} for the {role} role.",
                "extracted_at": BASE_TIME,
                "extracted_data": {
                    "role_category": role,
                    "responsibilities": ["Synthetic responsibility."],
                    "requirements": requirements,
                    "provider": {"ready": "true"},
                },
            }
        )

    # A trigger (migration 003) rejects tracker rows for inactive jobs.
    active_indices = [i for i, job in enumerate(jobs) if job["is_active"]]
    users, user_skills, user_jobs = [], [], []
    for u in range(USER_COUNT + (1 if heavy_rows else 0)):
        user_id = user_id_for(u)
        heavy = u == USER_COUNT
        users.append({"user_id": user_id, "full_name": "Heavy User" if heavy else f"User {u}"})
        k = rng.randint(USER_SKILLS_MIN, USER_SKILLS_MAX)
        user_skills.extend((user_id, s) for s in draw_skills(k))
        rows = heavy_rows if heavy else rng.randint(TRACKER_ROWS_MIN, TRACKER_ROWS_MAX)
        rows = min(rows, len(active_indices))
        for j in rng.sample(active_indices, rows):
            stamp = BASE_TIME - timedelta(minutes=rng.randint(0, 60 * 24 * 30))
            user_jobs.append((user_id, job_id_for(j), rng.choice(STATUSES), stamp))

    return {
        "jobs": jobs,
        "job_skills": job_skills,
        "documents": documents,
        "users": users,
        "user_skills": user_skills,
        "user_jobs": user_jobs,
    }


def seed(
    database_url: str,
    mongodb_uri: str,
    mongodb_database: str,
    n_jobs: int = DEFAULT_JOBS,
    seed_value: int = DEFAULT_SEED,
    heavy_rows: int = 0,
) -> dict[str, int]:
    """Replace the application data in the two disposable databases; returns row counts."""
    assert_local_urls(database_url, mongodb_uri)

    import psycopg2
    from psycopg2.extras import execute_values
    from pymongo import MongoClient

    conn = psycopg2.connect(database_url)
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT skill_id FROM public.skills ORDER BY skill_id")
            skill_ids = [row[0] for row in cur.fetchall()]
            if not skill_ids:
                raise RuntimeError("public.skills is empty; apply docs/DB/002_seed_skills.sql.")
            data = build_dataset(n_jobs, skill_ids, seed_value, heavy_rows)

            cur.execute("TRUNCATE public.users, public.jobs CASCADE")
            cur.execute("DELETE FROM auth.users")
            execute_values(
                cur,
                "INSERT INTO auth.users (id) VALUES %s",
                [(u["user_id"],) for u in data["users"]],
            )
            execute_values(
                cur,
                "INSERT INTO public.users (user_id, full_name) VALUES %s",
                [(u["user_id"], u["full_name"]) for u in data["users"]],
            )
            columns = (
                "job_id, source, external_job_id, title, company_name, location, job_type, "
                "work_arrangement, application_url, source_posted_at, is_active"
            )
            execute_values(
                cur,
                f"INSERT INTO public.jobs ({columns}) VALUES %s",
                [tuple(job[c.strip()] for c in columns.split(",")) for job in data["jobs"]],
                page_size=1000,
            )
            execute_values(
                cur,
                "INSERT INTO public.job_skills (job_id, skill_id, requirement_type) VALUES %s",
                data["job_skills"],
                page_size=5000,
            )
            execute_values(
                cur,
                "INSERT INTO public.user_skills (user_id, skill_id) VALUES %s",
                data["user_skills"],
            )
            execute_values(
                cur,
                "INSERT INTO public.user_jobs (user_id, job_id, status, created_at, updated_at)"
                " VALUES %s",
                [(u, j, s, t, t) for u, j, s, t in data["user_jobs"]],
                page_size=5000,
            )
    finally:
        conn.close()

    # VACUUM sets the visibility map (index-only scans) and ANALYZE refreshes statistics,
    # so the first timed query does not race autovacuum. It cannot run in a transaction.
    conn = psycopg2.connect(database_url)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("VACUUM (ANALYZE)")
    finally:
        conn.close()

    client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=10_000)
    try:
        collection = client[mongodb_database]["job_documents"]
        collection.delete_many({})
        for start in range(0, len(data["documents"]), 5000):
            collection.insert_many(data["documents"][start : start + 5000])
    finally:
        client.close()

    return {
        "jobs": len(data["jobs"]),
        "job_skills": len(data["job_skills"]),
        "users": len(data["users"]),
        "user_skills": len(data["user_skills"]),
        "user_jobs": len(data["user_jobs"]),
        "job_documents": len(data["documents"]),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--mongodb-uri", required=True)
    parser.add_argument("--mongodb-database", default="jobless_simulator_bench")
    parser.add_argument("--jobs", type=int, default=DEFAULT_JOBS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--heavy-tracker-rows", type=int, default=0)
    args = parser.parse_args(argv)
    try:
        counts = seed(
            args.database_url,
            args.mongodb_uri,
            args.mongodb_database,
            args.jobs,
            args.seed,
            args.heavy_tracker_rows,
        )
    except NotLocalError as exc:
        print(exc, file=sys.stderr)
        return 2
    print(counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
