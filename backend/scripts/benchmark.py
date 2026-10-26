"""WP-10 benchmark: indexes, SQL vs MongoDB, and the shared read lock, on DISPOSABLE databases.

Normally driven by ``scripts/run_benchmark.sh`` (which starts throwaway Docker containers,
applies docs/DB/001-003 and the Mongo collections script, runs this, and removes the
containers). Run by hand only against a disposable pair:

    cd backend
    uv run --no-env-file python scripts/benchmark.py \
        --database-url postgresql://postgres:postgres@127.0.0.1:5432/postgres \
        --mongodb-uri mongodb://127.0.0.1:27017/ --out ../docs/perf/results-2026-10-26.md

Every case runs 3 warm-up calls and then 30 timed calls and reports the median and p95 in
milliseconds. The code under test is the real backend code (``app.sql_discover``,
``app.sql_tracker``, ``app.skill_gap``, the FastAPI app for the throughput case); only the
database objects (indexes) and, in the throughput case, the lock dependency are toggled
from here. Nothing under backend/app/ is edited. It refuses any URL whose host is not
127.0.0.1 or localhost.
"""

import argparse
import json
import math
import os
import platform
import re
import secrets
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from collections.abc import Callable, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from seed_synthetic import (  # noqa: E402
    DEFAULT_JOBS,
    DEFAULT_SEED,
    USER_COUNT,
    assert_local_urls,
    seed,
    user_id_for,
)

WARMUPS = 3
RUNS = 30
TIME_WAIT_PAUSE_SECONDS = 45
# A phase with more than this share of failed requests is discarded and repeated (up to
# MAX_PHASE_ATTEMPTS times); every attempt's failure count is reported.
CLEAN_FAILURE_SHARE = 0.01
MAX_PHASE_ATTEMPTS = 3
THROUGHPUT_SECONDS = 30
THROUGHPUT_WORKERS = 10
HEAVY_TRACKER_ROWS = 2_000
# ABA order so a trend over time (cache, thermal, background work) is not confounded with
# the toggle: the first and last phases have the object, the middle one does not.
PHASES = (("with", True), ("without", False), ("with (repeat)", True))
MONGO_INDEX = "job_role_category"
SQL_INDEXES = (
    "jobs_active_type_arrangement_idx",
    "jobs_active_posted_at_idx",
    "user_jobs_user_status_idx",
)
COMMON_ROLE = "Software Engineering"
RARE_ROLE = "Quantum Computing"
# name -> (job_type, work_arrangement); the seed makes INTERNSHIP+REMOTE about 4% of jobs.
DISCOVER_FILTERS = {
    "no filter": (None, None),
    "broad (FULL_TIME, ONSITE, ~35% of jobs)": ("FULL_TIME", "ONSITE"),
    "selective (INTERNSHIP, REMOTE, ~4% of jobs)": ("INTERNSHIP", "REMOTE"),
}


# --------------------------------------------------------------------------- pure helpers


def percentile(values: Sequence[float], pct: float) -> float:
    """Linear-interpolation percentile (the same convention as numpy's default)."""
    if not values:
        raise ValueError("percentile of an empty sample")
    if not 0 <= pct <= 100:
        raise ValueError("pct must be between 0 and 100")
    ordered = sorted(values)
    position = (len(ordered) - 1) * pct / 100
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return float(ordered[low])
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def summarize(samples_ms: Sequence[float]) -> dict[str, float]:
    return {
        "n": len(samples_ms),
        "median": statistics.median(samples_ms),
        "p95": percentile(samples_ms, 95),
    }


def measure(fn: Callable[[], Any], warmups: int = WARMUPS, runs: int = RUNS) -> dict[str, float]:
    """Call ``fn`` ``warmups`` times untimed, then ``runs`` times timed (milliseconds)."""
    for _ in range(warmups):
        fn()
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    return summarize(samples)


def speedup(before_ms: float, after_ms: float) -> str:
    """'x1.8 faster' / 'x1.3 slower' / 'same' for the median pair (before -> after)."""
    if before_ms <= 0 or after_ms <= 0:
        return "n/a"
    ratio = before_ms / after_ms
    if abs(ratio - 1) < 0.05:
        return "about the same"
    return f"x{ratio:.1f} faster" if ratio > 1 else f"x{1 / ratio:.1f} slower"


def md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def fmt(ms: float) -> str:
    return f"{ms:.2f}" if ms < 100 else f"{ms:.0f}"


def plan_excerpt(plan_lines: Sequence[str], limit: int = 30) -> str:
    """Keep the plan's node lines (cost estimates stripped), sorts and the timings."""
    keep = re.compile(
        r"->|Sort Method|Rows Removed|Execution Time|Planning Time|^\s*(Sort|Limit|Hash|Merge)"
    )
    picked = []
    for line in plan_lines:
        if keep.search(line):
            picked.append(re.sub(r"\(cost=[^)]*\) ", "", line).rstrip()[:160])
    buffers = next((x.strip() for x in plan_lines if "Buffers:" in x), "")
    return "\n".join((picked[:limit]) + ([f"(top-level) {buffers}"] if buffers else []))


def extract_sql_index_ddl(sql_text: str, names: Sequence[str]) -> dict[str, str]:
    """The CREATE INDEX statement for each name, taken verbatim from migration 003."""
    found = {}
    for name in names:
        match = re.search(rf"CREATE INDEX {re.escape(name)}\b.*?;", sql_text, re.DOTALL)
        if match is None:
            raise RuntimeError(f"{name} not found in migration 003.")
        found[name] = match.group(0)
    return found


# --------------------------------------------------------------------------- environment


def configure_environment(database_url: str, mongodb_uri: str, mongodb_database: str) -> None:
    """Point the real app settings at the disposable pair (before any app import)."""
    assert_local_urls(database_url, mongodb_uri)
    os.environ["DATABASE_URL"] = database_url
    os.environ["MONGODB_URI"] = mongodb_uri
    os.environ["MONGODB_DATABASE"] = mongodb_database
    os.environ["APP_ENV"] = "development"
    from app.config import get_settings

    get_settings.cache_clear()


class KeepOpenConnection:
    """Proxy whose close() is a no-op, to time the query without connection set-up."""

    def __init__(self, conn):
        self._conn = conn

    def close(self) -> None:
        pass

    def __getattr__(self, name):
        return getattr(self._conn, name)


@contextmanager
def warm_connection(module, database_url: str):
    """Make ``module._connect`` hand out one long-lived connection while active."""
    import psycopg2

    conn = psycopg2.connect(database_url)
    conn.autocommit = True
    original = module._connect
    module._connect = lambda: KeepOpenConnection(conn)
    try:
        yield
    finally:
        module._connect = original
        conn.close()


def shell(*cmd: str) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def machine_context(pg, mongo_client) -> str:
    if sys.platform == "darwin":
        cpu = shell("sysctl", "-n", "machdep.cpu.brand_string")
        mem_bytes = shell("sysctl", "-n", "hw.memsize")
        memory = f"{int(mem_bytes) / 2**30:.0f} GiB" if mem_bytes.isdigit() else "unknown"
        if not cpu:  # sysctl can be blocked in sandboxes; system_profiler still answers
            profile = shell("system_profiler", "SPHardwareDataType")
            chip = re.search(r"^\s*Chip:\s*(.+)$", profile, re.MULTILINE)
            ram = re.search(r"^\s*Memory:\s*(.+)$", profile, re.MULTILINE)
            cpu = chip.group(1).strip() if chip else ""
            memory = ram.group(1).strip() if ram else memory
    else:
        cpu_lines = Path("/proc/cpuinfo").read_text().splitlines()
        cpu = next((x.split(":", 1)[1].strip() for x in cpu_lines if "model name" in x), "")
        memory = "unknown"
    docker = shell(
        "docker",
        "info",
        "--format",
        "Docker Engine {{.ServerVersion}}, {{.OperatingSystem}}, "
        "{{.NCPU}} CPUs, {{.MemTotal}} bytes memory for containers",
    )
    with pg.cursor() as cur:
        cur.execute("SHOW server_version")
        pg_version = cur.fetchone()[0]
    mongo_version = mongo_client.server_info().get("version", "?")
    import psycopg2
    import pymongo

    return "\n".join(
        [
            f"- CPU: {cpu or platform.processor() or 'unknown'} "
            f"({os.cpu_count()} logical cores), RAM {memory}",
            f"- OS: {platform.system()} {platform.release()} ({platform.machine()})",
            f"- {docker or 'Docker: unknown'}",
            f"- PostgreSQL {pg_version} and MongoDB {mongo_version} in containers "
            "(postgres:16, mongo:7), default settings, no tuning",
            f"- Python {platform.python_version()}, psycopg2 {psycopg2.__version__.split()[0]}, "
            f"pymongo {pymongo.version}",
        ]
    )


# --------------------------------------------------------------------------- case helpers


def execute_ddl(database_url: str, statements: Sequence[str]) -> None:
    import psycopg2

    conn = psycopg2.connect(database_url)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            for statement in statements:
                cur.execute(statement)
    finally:
        conn.close()


@contextmanager
def sql_indexes_dropped(database_url: str, names: Sequence[str], ddl: dict[str, str]):
    """Drop the named indexes for the block, then recreate them exactly as 003 defines."""
    execute_ddl(database_url, [f"DROP INDEX public.{name}" for name in names])
    try:
        yield
    finally:
        execute_ddl(database_url, [ddl[name] for name in names])


def explain_sql(database_url: str, sql: str, params: dict | tuple) -> list[str]:
    import psycopg2

    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute("EXPLAIN (ANALYZE, BUFFERS) " + sql, params)
            return [row[0] for row in cur.fetchall()]
    finally:
        conn.rollback()
        conn.close()


def explain_mongo(collection, filter_doc: dict) -> str:
    result = collection.database.command(
        {
            "explain": {
                "find": collection.name,
                "filter": filter_doc,
                "projection": {"job_id": 1, "_id": 0},
            },
            "verbosity": "executionStats",
        }
    )
    stats = result["executionStats"]
    stage = result["queryPlanner"]["winningPlan"]
    chain = []
    while stage:
        chain.append(stage["stage"])
        stage = stage.get("inputStage")
    return (
        f"winningPlan: {' -> '.join(chain)}\n"
        f"nReturned={stats['nReturned']} totalKeysExamined={stats['totalKeysExamined']} "
        f"totalDocsExamined={stats['totalDocsExamined']} "
        f"executionTimeMillis={stats['executionTimeMillis']}"
    )


def result_row(case: str, variant: str, setting: str, stats: dict[str, float]) -> dict[str, Any]:
    return {"case": case, "variant": variant, "setting": setting, **stats}


# --------------------------------------------------------------------------- the five cases


def run_discover(database_url: str, ddl: dict[str, str], user_id: str) -> tuple[list, dict]:
    from uuid import UUID

    from app import sql_discover
    from app.sql_discover import (
        DISCOVER_SQL,
        DiscoverFilters,
        PostgresDiscoverStore,
        query_parameters,
    )

    store = PostgresDiscoverStore()
    uid = UUID(user_id)
    names = SQL_INDEXES[:2]
    rows, plans = [], {}

    def feed(job_type, arrangement):
        flt = DiscoverFilters(job_type=job_type, work_arrangement=arrangement)
        return lambda: store.feed(uid, flt, 20, 0)

    selective = DISCOVER_FILTERS["selective (INTERNSHIP, REMOTE, ~4% of jobs)"]
    for label, enabled in PHASES:
        ctx = sql_indexes_dropped(database_url, names, ddl) if not enabled else nullcontext_()
        with ctx:
            for variant, (job_type, arrangement) in DISCOVER_FILTERS.items():
                rows.append(
                    result_row(
                        "1. Discover",
                        f"{variant}; new connection per call (real path)",
                        f"{label} partial indexes",
                        measure(feed(job_type, arrangement)),
                    )
                )
            with warm_connection(sql_discover, database_url):
                for variant, (job_type, arrangement) in DISCOVER_FILTERS.items():
                    rows.append(
                        result_row(
                            "1. Discover",
                            f"{variant}; warm connection (query cost only)",
                            f"{label} partial indexes",
                            measure(feed(job_type, arrangement)),
                        )
                    )
            flt = DiscoverFilters(job_type=selective[0], work_arrangement=selective[1])
            if label in ("with", "without"):
                plans[label] = plan_excerpt(
                    explain_sql(database_url, DISCOVER_SQL, query_parameters(uid, flt, 21, 0))
                )
    return rows, plans


def nullcontext_():
    from contextlib import nullcontext

    return nullcontext()


def run_skill_gap(database_url: str, mongo_db, user_id: str) -> tuple[list, str]:
    from uuid import UUID

    from app.skill_gap import (
        role_job_ids,
        skill_gap_mongo,
        skill_gap_pipeline,
        skill_gap_sql,
    )
    from app.sql_access import get_active_job_ids

    uid = UUID(user_id)
    rows = []
    active = get_active_job_ids()

    # Correctness first: both engines must give identical counts for every role timed here.
    notes = []
    for role in (COMMON_ROLE, RARE_ROLE):
        mongo_size, mongo_rows = skill_gap_mongo(mongo_db, active, role, uid)
        ids = role_job_ids(mongo_db, active, role)
        sql_size, sql_rows = skill_gap_sql(ids, uid)
        same = mongo_size == sql_size and [
            (r.skill_id, r.job_count, r.required_count) for r in mongo_rows
        ] == [(r.skill_id, r.job_count, r.required_count) for r in sql_rows]
        if not same:
            raise RuntimeError(f"Skill-gap engines disagree for {role!r}; benchmark is invalid.")
        notes.append(f"{role}: sample {mongo_size}, {len(mongo_rows)} skills, engines agree")

    for role in (COMMON_ROLE, RARE_ROLE):
        ids = role_job_ids(mongo_db, active, role)
        sample = len(ids)
        tag = f"{role} ({sample} postings)"
        rows.append(
            result_row(
                "2. Skill gap",
                tag,
                "MongoDB: aggregation only ($match + $facet)",
                measure(
                    lambda r=role: list(
                        mongo_db["job_documents"].aggregate(skill_gap_pipeline(active, r))
                    )
                ),
            )
        )
        rows.append(
            result_row(
                "2. Skill gap",
                tag,
                "MongoDB: skill_gap_mongo (aggregation + SQL names)",
                measure(lambda r=role: skill_gap_mongo(mongo_db, active, r, uid)),
            )
        )
        rows.append(
            result_row(
                "2. Skill gap",
                tag,
                "SQL: skill_gap_sql (role ids already known)",
                measure(lambda i=ids: skill_gap_sql(i, uid)),
            )
        )
        rows.append(
            result_row(
                "2. Skill gap",
                tag,
                "SQL end to end (Mongo role ids + skill_gap_sql)",
                measure(lambda r=role: skill_gap_sql(role_job_ids(mongo_db, active, r), uid)),
            )
        )
    return rows, "\n".join(f"- {n}" for n in notes)


def run_mongo_role_filter(mongo_db) -> tuple[list, dict]:
    collection = mongo_db["job_documents"]
    field = "extracted_data.role_category"
    rows, plans = [], {}
    for label, enabled in PHASES:
        if not enabled:
            collection.drop_index(MONGO_INDEX)
        try:
            for role in (COMMON_ROLE, RARE_ROLE):
                count = collection.count_documents({field: role})
                rows.append(
                    result_row(
                        "3. Mongo role filter",
                        f"{role} ({count} documents)",
                        f"{label} role_category index",
                        measure(
                            lambda r=role: list(
                                collection.find({field: r}, {"job_id": 1, "_id": 0})
                            )
                        ),
                    )
                )
            if label in ("with", "without"):
                plans[label] = explain_mongo(collection, {field: RARE_ROLE})
        finally:
            if not enabled:
                collection.create_index([(field, 1)], name=MONGO_INDEX)
    return rows, plans


def run_tracker(database_url: str, ddl: dict[str, str], busy_user: str, heavy_user: str | None):
    from uuid import UUID

    from app import sql_tracker

    store = sql_tracker.get_tracker_store()
    name = SQL_INDEXES[2]
    users = [("busiest seeded user", busy_user)]
    if heavy_user:
        users.append(
            (f"supplementary heavy user ({HEAVY_TRACKER_ROWS:,} tracker rows)", heavy_user)
        )
    rows, plans = [], {}
    for label, enabled in PHASES:
        ctx = nullcontext_() if enabled else sql_indexes_dropped(database_url, [name], ddl)
        with ctx:
            for who, user_id in users:
                uid = UUID(user_id)
                count = tracker_count(database_url, user_id)
                tag = f"{who}, {count} rows, status=SAVED"
                rows.append(
                    result_row(
                        "4. Tracker list",
                        f"{tag}; new connection per call (real path)",
                        f"{label} (user_id, status) index",
                        measure(lambda u=uid: store.list_items(u, ["SAVED"], 20, 0)),
                    )
                )
                with warm_connection(sql_tracker, database_url):
                    rows.append(
                        result_row(
                            "4. Tracker list",
                            f"{tag}; warm connection (query cost only)",
                            f"{label} (user_id, status) index",
                            measure(lambda u=uid: store.list_items(u, ["SAVED"], 20, 0)),
                        )
                    )
            target = heavy_user or busy_user
            sql = f"""
                SELECT {sql_tracker._ITEM_COLUMNS}, COUNT(*) OVER () AS total
                  FROM public.user_jobs AS t
                  JOIN public.jobs AS j ON j.job_id = t.job_id
                 WHERE t.user_id = %s
                   AND (%s::text[] IS NULL OR t.status = ANY(%s::text[]))
                 ORDER BY t.updated_at DESC, t.job_id
                 LIMIT %s OFFSET %s"""
            if label in ("with", "without"):
                plans[label] = plan_excerpt(
                    explain_sql(database_url, sql, (target, ["SAVED"], ["SAVED"], 20, 0))
                )
    return rows, plans


def tracker_count(database_url: str, user_id: str) -> int:
    import psycopg2

    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM public.user_jobs WHERE user_id = %s", (user_id,))
            return cur.fetchone()[0]
    finally:
        conn.close()


def busiest_user(database_url: str) -> str:
    import psycopg2

    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id FROM public.user_jobs GROUP BY user_id "
                "HAVING user_id <> %s ORDER BY count(*) DESC, user_id LIMIT 1",
                (user_id_for(USER_COUNT),),
            )
            return str(cur.fetchone()[0])
    finally:
        conn.close()


def unsigned_token(user_id: str) -> str:
    import jwt

    return jwt.encode({"sub": user_id}, None, algorithm="none")


def free_local_port() -> int:
    """A currently free port on 127.0.0.1 (the identity check guards the small race)."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def run_throughput(
    database_url: str, mongodb_uri: str, mongodb_database: str, user_ids: Sequence[str]
) -> list[dict[str, Any]]:
    import httpx

    results = []
    for position, (label, no_lock) in enumerate(
        (
            ("with shared read lock", "0"),
            ("without shared read lock", "1"),
            ("with shared read lock (repeat)", "0"),
        )
    ):
        if position:
            # Every request opens fresh TCP connections to PostgreSQL (there is no pool).
            # Let the first run's TIME_WAIT sockets drain so the second run does not
            # start close to local ephemeral-port exhaustion.
            time.sleep(TIME_WAIT_PAUSE_SECONDS)
        attempts: list[dict[str, Any]] = []
        for attempt in range(MAX_PHASE_ATTEMPTS):
            if attempt:
                time.sleep(TIME_WAIT_PAUSE_SECONDS)
            token = secrets.token_hex(16)
            error_log = Path(tempfile.mkdtemp(prefix="bench-")) / f"server-errors-{position}.jsonl"
            port = free_local_port()
            env = {
                "PATH": os.environ.get("PATH", ""),
                "HOME": os.environ.get("HOME", ""),
                "DATABASE_URL": database_url,
                "MONGODB_URI": mongodb_uri,
                "MONGODB_DATABASE": mongodb_database,
                "APP_ENV": "development",
                "AUTH_ALLOW_UNVERIFIED_TOKENS": "true",
                "BENCH_NO_READ_LOCK": no_lock,
                "BENCH_TOKEN": token,
                "BENCH_ERROR_LOG": str(error_log),
            }
            server = subprocess.Popen(
                [
                    sys.executable,
                    str(Path(__file__).with_name("bench_server.py")),
                    "--port",
                    str(port),
                ],
                env=env,
                cwd=BACKEND_DIR,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                base = f"http://127.0.0.1:{port}"
                expected = {"token": token, "no_read_lock": no_lock == "1"}
                for _ in range(60):
                    if server.poll() is not None:
                        raise RuntimeError(
                            f"The benchmark server exited with status {server.poll()}."
                        )
                    try:
                        reply = httpx.get(f"{base}/__bench/identity", timeout=2)
                        if reply.status_code == 200:
                            if reply.json() != expected:
                                raise RuntimeError(
                                    "Another server answered; refusing to measure it."
                                )
                            break
                    except httpx.HTTPError:
                        time.sleep(0.5)
                else:
                    raise RuntimeError("The benchmark server did not start.")
                result = _drive(base, label, user_ids, database_url)
                result["server_errors"] = summarize_server_log(error_log)
                attempts.append(result)
            finally:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()
            clean = attempts[-1]["errors"] <= CLEAN_FAILURE_SHARE * (
                attempts[-1]["requests"] + attempts[-1]["errors"]
            )
            if clean:
                break
        chosen = attempts[-1]
        chosen["attempt_failures"] = [a["errors"] for a in attempts]
        chosen["contaminated"] = not clean
        results.append(chosen)
    return results


def summarize_server_log(path: Path) -> dict[str, int]:
    """Counts of distinct cause chains the server logged for its 5xx responses."""
    counts: Counter = Counter()
    if path.exists():
        for line in path.read_text().splitlines():
            record = json.loads(line)
            counts[" <- ".join(re.sub(r"port \d+", "port N", c) for c in record["chain"])] += 1
    return dict(counts.most_common(5))


class HostSampler(threading.Thread):
    """Samples PostgreSQL session count and the host's TIME_WAIT sockets while load runs."""

    def __init__(self, database_url: str):
        super().__init__(daemon=True)
        self.database_url = database_url
        self.stop = threading.Event()
        self.max_sessions = 0
        self.max_time_wait = None  # None: could not be measured
        self.max_connections = None

    def run(self) -> None:
        import psycopg2

        conn = psycopg2.connect(self.database_url)
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute("SHOW max_connections")
                self.max_connections = int(cur.fetchone()[0])
                while not self.stop.is_set():
                    cur.execute(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE backend_type = 'client backend'"
                    )
                    self.max_sessions = max(self.max_sessions, cur.fetchone()[0])
                    out = shell("netstat", "-an", "-p", "tcp")
                    if out:  # empty when netstat is blocked (some sandboxes): then unknown
                        self.max_time_wait = max(self.max_time_wait or 0, out.count("TIME_WAIT"))
                    self.stop.wait(1.0)
        finally:
            conn.close()


def _drive(base: str, label: str, user_ids: Sequence[str], database_url: str) -> dict[str, Any]:
    import random

    import httpx

    queries = [
        "limit=20",
        "limit=20&job_type=FULL_TIME&work_arrangement=ONSITE",
        "limit=20&job_type=INTERNSHIP&work_arrangement=REMOTE",
    ]

    detail: Counter = Counter()
    error_times: list[float] = []
    run_started = [0.0]

    def describe_error(response) -> str:
        """The API error code and message for a failed response, or the client exception."""
        if isinstance(response, Exception):
            return f"client {type(response).__name__}"
        try:
            error = response.json()["error"]
            return f"{response.status_code} {error['code']}: {error['message']}"
        except (ValueError, KeyError, TypeError):
            return f"{response.status_code} (unparsed body)"

    def worker(index: int, stop_at: float, latencies: list, errors: list) -> None:
        rng = random.Random(index)
        user = user_ids[index % len(user_ids)]
        headers = {"Authorization": f"Bearer {unsigned_token(user)}"}
        with httpx.Client(base_url=base, headers=headers, timeout=60) as client:
            while time.perf_counter() < stop_at:
                start = time.perf_counter()
                response = None
                try:
                    response = client.get(f"/api/discover?{rng.choice(queries)}")
                    status = response.status_code
                except httpx.HTTPError as exc:
                    status = -1
                    response = exc
                elapsed = (time.perf_counter() - start) * 1000
                if status == 200:
                    latencies.append(elapsed)
                else:
                    errors.append(status)
                    error_times.append(time.perf_counter() - run_started[0])
                    detail[describe_error(response)] += 1

    def run(seconds: float) -> tuple[list, list, float]:
        latencies: list[float] = []
        errors: list[int] = []
        started = time.perf_counter()
        run_started[0] = started
        error_times.clear()
        stop_at = started + seconds
        threads = [
            threading.Thread(target=worker, args=(i, stop_at, latencies, errors))
            for i in range(THROUGHPUT_WORKERS)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return latencies, errors, time.perf_counter() - started

    run(3)  # warm-up: server threads, connections, caches
    sampler = HostSampler(database_url)
    sampler.start()
    latencies, errors, elapsed = run(THROUGHPUT_SECONDS)
    sampler.stop.set()
    sampler.join(timeout=10)
    if not latencies:
        raise RuntimeError(f"No successful requests ({label}); errors: {errors[:5]}")
    stats = summarize(latencies)
    codes = {str(code): errors.count(code) for code in sorted(set(errors))}
    return {
        "setting": label,
        "requests": len(latencies),
        "errors": len(errors),
        "error_codes": codes,
        "error_bodies": dict(detail.most_common(5)),
        "error_window_s": (
            [round(min(error_times), 1), round(max(error_times), 1)] if error_times else None
        ),
        "max_pg_sessions": sampler.max_sessions,
        "max_connections": sampler.max_connections,
        "max_time_wait": sampler.max_time_wait,
        "rps": len(latencies) / elapsed,
        "median": stats["median"],
        "p95": stats["p95"],
    }


# --------------------------------------------------------------------------- report


def pair_table(rows: Sequence[dict[str, Any]]) -> str:
    """With/without/with-again triples (cases 1, 3, 4): medians and the ratio."""
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in rows:
        grouped.setdefault((r["case"], r["variant"]), []).append(r)
    body = []
    for (case, variant), group in grouped.items():
        if len(group) != 3:
            continue
        first, without, again = group
        with_mean = (first["median"] + again["median"]) / 2
        body.append(
            (
                case,
                variant,
                fmt(first["median"]),
                fmt(without["median"]),
                fmt(again["median"]),
                f"{speedup(without['median'], with_mean)} with the index",
            )
        )
    return md_table(
        [
            "Case",
            "Variant",
            "With: median (ms)",
            "Without: median (ms)",
            "With, repeated: median (ms)",
            "Effect (without vs mean of the two with)",
        ],
        body,
    )


def long_table(rows: Sequence[dict[str, Any]]) -> str:
    return md_table(
        ["Case", "Variant", "Setting", "Median (ms)", "p95 (ms)", "Runs"],
        [
            (r["case"], r["variant"], r["setting"], fmt(r["median"]), fmt(r["p95"]), r["n"])
            for r in rows
        ],
    )


def fenced(text: str) -> str:
    return f"```\n{text}\n```"


def run_size(args, n_jobs: int, ddl: dict[str, str], with_throughput: bool) -> dict[str, Any]:
    import psycopg2
    from pymongo import MongoClient

    counts = seed(
        args.database_url,
        args.mongodb_uri,
        args.mongodb_database,
        n_jobs,
        args.seed,
        HEAVY_TRACKER_ROWS,
    )
    configure_environment(args.database_url, args.mongodb_uri, args.mongodb_database)
    execute_ddl(args.database_url, ["ANALYZE"])  # once; index toggles must not re-analyze
    time.sleep(5)  # let background work from the bulk load (checkpoints, Mongo journal) settle
    client = MongoClient(args.mongodb_uri, directConnection=True)
    mongo_db = client[args.mongodb_database]
    pg = psycopg2.connect(args.database_url)
    pg.autocommit = True
    try:
        user_ids = [user_id_for(i) for i in range(USER_COUNT)]
        out: dict[str, Any] = {"n_jobs": n_jobs, "counts": counts, "rows": []}
        print(f"[{n_jobs}] case 1: Discover", flush=True)
        rows, out["discover_plans"] = run_discover(args.database_url, ddl, user_ids[0])
        out["rows"] += rows
        print(f"[{n_jobs}] case 2: skill gap", flush=True)
        rows, out["skill_gap_notes"] = run_skill_gap(args.database_url, mongo_db, user_ids[0])
        out["rows"] += rows
        print(f"[{n_jobs}] case 3: Mongo role filter", flush=True)
        rows, out["mongo_plans"] = run_mongo_role_filter(mongo_db)
        out["rows"] += rows
        print(f"[{n_jobs}] case 4: tracker list", flush=True)
        rows, out["tracker_plans"] = run_tracker(
            args.database_url, ddl, busiest_user(args.database_url), user_id_for(USER_COUNT)
        )
        out["rows"] += rows
        if with_throughput:
            print(f"[{n_jobs}] case 5: throughput ({THROUGHPUT_SECONDS}s x2)", flush=True)
            out["throughput"] = run_throughput(
                args.database_url, args.mongodb_uri, args.mongodb_database, user_ids[:10]
            )
            print(f"[{n_jobs}] case 5 control: raw connection storm", flush=True)
            out["storm"] = run_connection_storm(args.database_url)
        out["context"] = machine_context(pg, client)
        return out
    finally:
        pg.close()
        client.close()


def render(args, sections: list[dict[str, Any]]) -> str:
    first = sections[0]
    parts = [
        "# INF2003 performance results (WP-10)",
        "",
        "Generated by `bash backend/scripts/run_benchmark.sh` on 2026-10-26. Every number below "
        "was measured on throwaway local Docker databases seeded with synthetic data; nothing "
        "is estimated. See [README.md](README.md) for how to run it and how to read the tables.",
        "",
        "## Machine and context",
        "",
        first["context"],
        f"- Timing: {WARMUPS} warm-up calls, then {RUNS} timed calls per row; median and p95 "
        f"(linear interpolation) in milliseconds. Random seed {args.seed}.",
        "",
    ]
    for section in sections:
        n = section["n_jobs"]
        c = section["counts"]
        primary = section is first
        title = "primary run" if primary else "larger run (supplementary)"
        parts += [
            f"## {n:,} jobs ({title})",
            "",
            f"Seeded rows: {c['jobs']:,} jobs, {c['job_skills']:,} job_skills, {c['users']} users "
            f"(50 per the PRD plus one heavy tracker user), {c['user_skills']} user_skills, "
            f"{c['user_jobs']:,} tracker rows, {c['job_documents']:,} Mongo job documents.",
            "",
            "### Results",
            "",
            long_table(section["rows"]),
            "",
            "With / without / with again (ABA order), medians only (cases 1, 3, 4). "
            'If the two "with" columns disagree by more than the effect, it is noise:',
            "",
            pair_table(section["rows"]),
            "",
        ]
        if "throughput" in section:
            parts += [
                f"### 5. Throughput: Discover, {THROUGHPUT_WORKERS} concurrent workers, "
                f"{THROUGHPUT_SECONDS} s",
                "",
                md_table(
                    [
                        "Setting",
                        "Requests (200 OK)",
                        "Failed (status: count)",
                        "Requests/s",
                        "Median (ms)",
                        "p95 (ms)",
                    ],
                    [
                        (
                            t["setting"],
                            t["requests"],
                            t["error_codes"] or "none",
                            f"{t['rps']:.1f}",
                            fmt(t["median"]),
                            fmt(t["p95"]),
                        )
                        for t in section["throughput"]
                    ],
                ),
                "",
                "Failure and host diagnostics per phase (maximum observed during the 30 s; "
                "PostgreSQL sessions are `client backend` rows in `pg_stat_activity`, sampled "
                "once a second; TIME_WAIT is the host's `netstat` count):",
                "",
                md_table(
                    [
                        "Setting",
                        "Max PG sessions / max_connections",
                        "Max host TIME_WAIT",
                        "Seconds into the phase when failures occurred",
                        "Client-side failure bodies",
                        "Server-side cause chains (5xx)",
                    ],
                    [
                        (
                            t["setting"]
                            + (
                                f" (attempts' failures: {t['attempt_failures']}"
                                + ("; STILL CONTAMINATED" if t["contaminated"] else "")
                                + ")"
                            ),
                            f"{t['max_pg_sessions']} / {t['max_connections']}",
                            "not measurable" if t["max_time_wait"] is None else t["max_time_wait"],
                            t["error_window_s"] or "none",
                            t["error_bodies"] or "none",
                            t["server_errors"] or "none",
                        )
                        for t in section["throughput"]
                    ],
                ),
                "",
                "A phase with more than 1% failed requests is discarded and repeated (up to 3 "
                "attempts, with a cooldown); the first column of the table above notes every "
                "attempt's failure count, so discarded attempts are disclosed. The failures are "
                "explained by the control experiment below.",
                "",
                f"#### Control: raw connection storm, no application code ({THROUGHPUT_WORKERS} "
                f"threads, {THROUGHPUT_SECONDS} s)",
                "",
                md_table(
                    [
                        "Pattern",
                        "Successful iterations",
                        "Failed connection attempts",
                        "Seconds into the phase when failures occurred",
                        "Connections/s (successful)",
                        "Most common failure",
                    ],
                    [
                        (
                            c["setting"],
                            c["iterations_ok"],
                            c["failures"],
                            c["failure_window_s"] or "none",
                            f"{c['connections_per_s']:.0f}",
                            next(iter(c["failure_messages"]), "none"),
                        )
                        for c in section["storm"]
                    ],
                ),
                "",
                "Each worker is a keep-alive `httpx` client for one seeded user and picks one of "
                "three Discover queries (no filter, broad filter, selective filter) at random. "
                "The server is the real FastAPI app on a free `127.0.0.1` port, "
                "identity-checked before load starts, with unsigned "
                'development tokens; the "without" run replaces the route\'s lock with a no-op.',
                "",
            ]
        parts += [
            "### Skill-gap correctness check",
            "",
            section["skill_gap_notes"],
            "",
            "### Query plans",
            "",
            "Discover, selective filter, `EXPLAIN (ANALYZE, BUFFERS)` (excerpt), with the partial "
            "indexes:",
            "",
            fenced(section["discover_plans"]["with"]),
            "",
            "Same statement without them:",
            "",
            fenced(section["discover_plans"]["without"]),
            "",
            f'MongoDB role filter for "{RARE_ROLE}" (`explain("executionStats")`), with the index:',
            "",
            fenced(section["mongo_plans"]["with"]),
            "",
            "Without it:",
            "",
            fenced(section["mongo_plans"]["without"]),
            "",
            "Tracker list for the heavy user (status SAVED, LIMIT 20), with the "
            "`(user_id, status)` index:",
            "",
            fenced(section["tracker_plans"]["with"]),
            "",
            "Without it:",
            "",
            fenced(section["tracker_plans"]["without"]),
            "",
        ]
    return "\n".join(parts).rstrip() + "\n"


STORM_PHASES = (
    ("2 nested connections per iteration (the lock path's pattern)", 2),
    ("1 connection per iteration (the no-lock path's pattern)", 1),
    ("2 nested connections per iteration (repeat)", 2),
)
STORM_PAUSE_SECONDS = 20


def run_connection_storm(database_url: str) -> list[dict[str, Any]]:
    """Control experiment with no application code: THROUGHPUT_WORKERS threads open (and close)
    raw psycopg2 connections in a loop and run SELECT 1, 3 s warm-up then THROUGHPUT_SECONDS.
    If these fail too, the failures come from the connection path, not from the app."""
    import psycopg2

    results = []
    for position, (label, nested) in enumerate(STORM_PHASES):
        if position:
            time.sleep(STORM_PAUSE_SECONDS)

        def phase(seconds: float):
            ok, failures, times = [0], Counter(), []
            guard = threading.Lock()
            started = time.perf_counter()

            def worker() -> None:
                while time.perf_counter() < started + seconds:
                    try:
                        outer = psycopg2.connect(database_url)
                        try:
                            if nested == 2:
                                inner = psycopg2.connect(database_url)
                                inner.close()
                            with outer.cursor() as cur:
                                cur.execute("SELECT 1")
                        finally:
                            outer.close()
                        with guard:
                            ok[0] += 1
                    except psycopg2.Error as exc:
                        text = (str(exc).strip().splitlines() or [""])[0]
                        with guard:
                            failures[
                                f"{type(exc).__name__}: {re.sub(r'port \d+', 'port N', text)}"
                            ] += 1
                            times.append(time.perf_counter() - started)

            threads = [threading.Thread(target=worker) for _ in range(THROUGHPUT_WORKERS)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            return ok[0], failures, times, time.perf_counter() - started

        phase(3)
        ok, failures, times, elapsed = phase(THROUGHPUT_SECONDS)
        results.append(
            {
                "setting": label,
                "iterations_ok": ok,
                "failures": sum(failures.values()),
                "failure_messages": dict(failures.most_common(3)),
                "failure_window_s": [round(min(times), 1), round(max(times), 1)] if times else None,
                "connections_per_s": ok * nested / elapsed,
            }
        )
    return results


def diagnose_throughput(args) -> int:
    """Seed the first size, run only case 5 and print the table and diagnostics as JSON."""
    size = int(args.sizes.split(",")[0])
    seed(
        args.database_url,
        args.mongodb_uri,
        args.mongodb_database,
        size,
        args.seed,
        HEAVY_TRACKER_ROWS,
    )
    configure_environment(args.database_url, args.mongodb_uri, args.mongodb_database)
    user_ids = [user_id_for(i) for i in range(10)]
    rows = run_throughput(args.database_url, args.mongodb_uri, args.mongodb_database, user_ids)
    print(json.dumps(rows, indent=2))
    print(json.dumps(run_connection_storm(args.database_url), indent=2))
    return 0


def set_throughput_seconds(seconds: int) -> None:
    global THROUGHPUT_SECONDS
    THROUGHPUT_SECONDS = seconds


def set_workers(workers: int) -> None:
    global THROUGHPUT_WORKERS
    THROUGHPUT_WORKERS = workers


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--mongodb-uri", required=True)
    parser.add_argument("--mongodb-database", default="jobless_simulator_bench")
    parser.add_argument("--sizes", default=str(DEFAULT_JOBS), help="comma-separated job counts")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out", default="")
    parser.add_argument("--skip-throughput", action="store_true")
    parser.add_argument(
        "--only-throughput",
        action="store_true",
        help="seed the first size and run only case 5 (diagnostics; output is not a full report)",
    )
    parser.add_argument("--workers", type=int, default=THROUGHPUT_WORKERS)
    parser.add_argument("--throughput-seconds", type=int, default=30)
    args = parser.parse_args(argv)
    assert_local_urls(args.database_url, args.mongodb_uri)
    set_throughput_seconds(args.throughput_seconds)
    set_workers(args.workers)

    ddl = extract_sql_index_ddl(
        (REPO_ROOT / "docs/DB/003_views_triggers_indexes.sql").read_text(), SQL_INDEXES
    )
    if args.only_throughput:
        return diagnose_throughput(args)
    sections = []
    for position, size in enumerate(int(s) for s in args.sizes.split(",")):
        sections.append(
            run_size(args, size, ddl, with_throughput=position == 0 and not args.skip_throughput)
        )
    Path(args.out).write_text(render(args, sections))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
