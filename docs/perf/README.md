# Performance analysis (WP-10)

Measured numbers for the report and presentation: indexes on/off, MongoDB aggregation vs the
SQL implementation of the same question, and the cost of the shared read lock. Everything is
measured on throwaway local Docker databases seeded with synthetic data. The latest output is
[results-2026-10-27.md](results-2026-10-27.md) (after connection reuse); the run before it is
[results-2026-10-26.md](results-2026-10-26.md).

## Run it

Prerequisites: Docker running, `uv`, and the backend dependencies resolvable (`uv` syncs them).

```bash
bash backend/scripts/run_benchmark.sh              # from the repo root; about 8-10 minutes
BENCH_SIZES=5000 bash backend/scripts/run_benchmark.sh   # primary run only, faster
BENCH_OUT=docs/perf/my-run.md bash backend/scripts/run_benchmark.sh   # default: docs/perf/results-<today>.md
```

The wrapper starts `postgres:16` and `mongo:7` on random `127.0.0.1` ports, creates the
Supabase role/`auth.users` stand-ins, applies `docs/DB/001`, `002`, `003` and the Mongo
collections script, seeds, benchmarks, writes the results file and removes both containers on
exit (also on Ctrl-C or failure). The throughput server listens on a free `127.0.0.1` port picked at run time (never 5173 or
8000) and is identity-checked before any load is sent. No `.env` file is read.

What the code guarantees about destinations: the scripts refuse to run (before any connection)
unless the PostgreSQL URL's *effective* libpq parameters (via `psycopg2.extensions.parse_dsn`,
so `?host=`, `?hostaddr=`, comma-separated multi-host lists and `service` files are caught) all
name `127.0.0.1`/`localhost`, and the MongoDB URI is a single `127.0.0.1`/`localhost` node
(no `mongodb+srv`, no seed lists; connections use `directConnection`). They also refuse to start
if `PGHOST`, `PGHOSTADDR`, `PGSERVICE` or `PGSERVICEFILE` is set, and the wrapper unsets them.
This is a guard against mistakes, not a sandbox: IPv6 (`::1`) is rejected as unsupported.
Cleanup: the wrapper removes both containers by unique name on exit, Ctrl-C, SIGTERM or
failure; a `kill -9` of the wrapper itself cannot be trapped, so check `docker ps -a` if you
force-kill it.

Files: `backend/scripts/seed_synthetic.py` (data), `backend/scripts/benchmark.py` (cases and
report), `backend/scripts/bench_server.py` (local server for the throughput case),
`backend/tests/test_benchmark_helpers.py` (localhost guard, percentile maths, seed shape).

## What each case measures

Each row is 3 warm-up calls, then 30 timed calls; the table shows the median and p95 in ms.
The code under test is the real backend code; only database objects (indexes) are toggled from
the benchmark (statistics are refreshed once before the toggling starts, not at each toggle), and in case 5 the lock is swapped for a no-op in `bench_server.py` (no file under
`backend/app/` is changed).

| Case | What is timed | Toggle |
|---|---|---|
| 1. Discover | `PostgresDiscoverStore.feed` (the ranked feed query) for three filter shapes: none, broad (about 35% of jobs), selective (about 4%) | drop/recreate `jobs_active_type_arrangement_idx` and `jobs_active_posted_at_idx` |
| 2. Skill gap | The same role through MongoDB (`$match` + `$facet` aggregation, alone and as `skill_gap_mongo`) and through SQL (`skill_gap_sql` with the role's job ids, and end to end including the Mongo lookup of those ids). A common role and a rare one. The run first checks that both engines return identical counts | none (engine comparison) |
| 3. Mongo role filter | `find({"extracted_data.role_category": role})`, common and rare role | drop/recreate `job_role_category` |
| 4. Tracker list | `PostgresTrackerStore.list_items` (status SAVED, first page) for the busiest of the 50 seeded users and for one supplementary heavy user with 2,000 tracker rows | drop/recreate `user_jobs_user_status_idx` |
| 5. Throughput | 10 concurrent `httpx` workers call `GET /api/discover` for 30 s against the real FastAPI app, with the shared job read lock and with it replaced by a no-op | lock on/off |

Cases 1 and 4 have two variants. "App connection handling" is the real path: whatever
`backend/app/sql_db.py` does (since the connection-reuse change, a connection from its idle pool;
in the 2026-10-26 run, labelled "new connection per call", a fresh connection every call).
"Warm connection" reuses one connection, so it shows the query cost without connection set-up;
use it to judge the index, use the first to judge what a user would feel.

## Reading the results

- Every table lists median and p95. Compare medians for the typical case and p95 for the
  worst-case-ish tail. With 30 samples, p95 is close to the 2nd-slowest run.
- Cases 1, 3 and 4 and the throughput case run in ABA order: with the object, without it, with
  it again. The "With vs without" table shows all three medians. If the two "with" columns
  differ from each other by as much as "without" differs from them, the effect is noise (a
  laptop drifts by up to about 20% between phases). The EXPLAIN excerpts show what the planner
  actually did, which is better evidence than any ratio.
- Sizes: the primary run is 5,000 jobs (the PRD size); a 50,000-job run shows how the numbers
  scale. Row counts are in each section.
- Seed distribution: 8 role categories (the rarest, "Quantum Computing", is about 1%); job
  type 70/10/20% full-time/part-time/internship; work arrangement 50/30/20% onsite/hybrid/
  remote; skill popularity is Zipf-like; 5% of jobs are inactive; a requirement is REQUIRED
  60% of the time.

## What the committed runs showed (for the report author)

Two official runs, both on the team's own machine (Apple M5, Docker Desktop), outside any
sandbox, with `bash backend/scripts/run_benchmark.sh`:

- [results-2026-10-26.md](results-2026-10-26.md): **before** connection reuse (the app opened a
  new PostgreSQL connection per call).
- [results-2026-10-27.md](results-2026-10-27.md): **after** connection reuse
  (`backend/app/sql_db.py` parks closed connections in a small idle pool). **Quote this run**
  for indexes and engines; quote both for the before/after finding.

Timings vary by a few tens of percent between runs; compare within a run, and re-run before
quoting new numbers.

- **The MongoDB `role_category` index is the clear win, and it grows with data.** A rare role
  (about 1% of documents) is about 4x faster at 5,000 documents (0.28 and 0.32 ms with the index
  vs 1.24 ms without) and about 11x at 50,000 (1.31 and 1.27 ms vs 14.9 ms). The plan changes
  from COLLSCAN (every document examined) to IXSCAN (only matches). A common role (about 30% of
  documents) gains only about 1.2-1.3x, because most documents match. The before run agrees
  (about 3.6x and 9x).
- **The Discover partial indexes help a little, only at 50,000 jobs, only for selective
  filters.** At 5,000 jobs every variant is "about the same". At 50,000 jobs the selective filter
  (about 4% of jobs) is about 1.3x faster with the indexes on both the real path and a warm
  connection (9.9 ms vs 13.4 ms); the broad filter shows no gain, and the no-filter row is
  uncertain (its two "with" phases disagree: 145 vs 186 ms). The cost that remains is joining
  and ranking `job_skills` for every candidate job, which no index on `jobs` removes. The before
  run reported 1.5-2.2x on the real path; that did not reproduce, so use the smaller figure.
  `jobs_active_posted_at_idx` is not used by Discover (its ORDER BY starts with the computed
  coverage).
- **The tracker `(user_id, status)` index does nothing measurable here.** Every variant is
  within about 1.1x either way, at both sizes and in both runs. Users have at most 50 tracker
  rows (the supplementary heavy user 2,000), and the primary key `(user_id, job_id)` already
  finds a user's rows directly. An earlier draft claimed 1.6-1.9x; that came from refreshing
  planner statistics at the moment the index was dropped, and disappeared once the method was
  fixed.
- **SQL vs MongoDB for skill gap: SQL is faster once connections are reused.**

  | Role, size | Mongo aggregation alone | `skill_gap_sql` alone (job ids known) | `skill_gap_mongo` end to end | SQL end to end (Mongo ids + SQL) |
  |---|---|---|---|---|
  | common, 5,000 | 14.2 ms | 6.8 ms | 15.6 ms | 11.4 ms |
  | rare, 5,000 | 2.7 ms | 1.4 ms | 3.8 ms | 3.2 ms |
  | common, 50,000 | 214 ms | 80 ms | 216 ms | 143 ms |
  | rare, 50,000 | 34.1 ms | 9.5 ms | 36.1 ms | 38.4 ms |

  - The SQL query alone is 1.9-3.6x faster than the aggregation: it joins narrow indexed rows
    instead of unwinding and regrouping documents.
  - End to end, SQL still needs the role's job ids, which only Mongo stores. With that lookup
    included, SQL is about 1.4-1.5x faster for the common role; for the rare role it is about
    1.2x faster at 5,000 jobs and about equal at 50,000. Mongo's path also returns `minimum_years`, which SQL cannot.
  - **Before connection reuse the comparison was unfair to SQL.** pymongo's client keeps its
    own connection pool, but every SQL call paid for a new connection. In the before run, SQL
    alone was *slower* than Mongo at 5,000 jobs (17.3 vs 14.4 ms) and end to end was a tie
    (23.7 vs 24.0 ms). The Mongo aggregation timing barely changed between runs (14.4 → 14.2
    ms); the timings with a SQL step fell by about 4-12 ms each, which is the connection set-up
    cost. Say this in
    the report: a fair engine comparison needs the same connection handling on both sides.
- **Throughput and the shared read lock.** 10 concurrent workers, 30 s per phase, Discover:

  | Run | Phase | Successful req/s | Failed requests | Peak host TIME_WAIT | Peak PostgreSQL sessions |
  |---|---|---|---|---|---|
  | before | with lock | 143.4 | 8,170 (HTTP 503) | 16,085 | 18 / 100 |
  | before | without lock | 230.6 | none | 7,454 | 12 / 100 |
  | before | with lock (repeat) | 156.4 | 4,335 (HTTP 503) | 14,021 | 19 / 100 |
  | after | with lock | 369.8 | none | 44 | 24 / 100 |
  | after | without lock | 240.2 | none | 16 | 13 / 100 |
  | after | with lock (repeat) | 250.6 | none | 14 | 25 / 100 |

  - Connection reuse removed every failure: the lock phases went from 12,505 failed requests to
    none, and successful throughput with the lock rose from 143-156 to 251-370 req/s.
  - The lock's own cost is no longer measurable in this setup: the two with-lock phases of the
    after run disagree by about 48% (370 vs 251 req/s), and the no-lock phase (240) is slower
    than both, so drift between phases is larger than any lock effect.
    The before run's "32-38% less with the lock" was mostly the second connection's set-up cost
    and the failures, not the lock. The phase-to-phase drift itself (the first phase is fastest)
    was not investigated; a laptop's thermal and background load are the likely cause.
  - The benchmark has no concurrent writer, so it measures the lock's overhead, not its benefit
    (blocking readers while an admin refresh rewrites jobs); say so in the report.
- **Finding: per-call connections exhausted the host's outgoing ports (fixed).**
  - In the before run, both with-lock phases returned HTTP 503 `service_unavailable`. The
    server-side cause chain is `ApiError <- SqlAccessError <- psycopg2.OperationalError:
    connection to server at "127.0.0.1", port N failed: server closed the connection
    unexpectedly`: opening the lock's PostgreSQL connection failed. It is not a lock timeout
    (that would be SQLSTATE 55P03).
  - PostgreSQL was not the limit (18-19 of 100 sessions). The host was: sockets in TIME_WAIT
    reached 16,085 against macOS's default range of 16,384 outgoing (ephemeral) ports
    (49152-65535; check yours with
    `sysctl net.inet.ip.portrange.first net.inet.ip.portrange.last`), and failures began 22.6 s
    and 25.9 s into the phases, once TIME_WAIT had built up.
  - Why: the app opened a fresh PostgreSQL connection per call, and the lock path opened a
    second one per request. Each closed connection holds its port in TIME_WAIT for about 30 s,
    so twice the connection rate filled the port range within a 30-second phase.
  - Fix: `backend/app/sql_db.py` reuses connections. `close()` rolls a connection back and parks
    it in an idle pool (up to 20 per process, each reused for at most 60 s idle); the next
    request takes it. Callers did not change.
  - Evidence the fix is the cause: in the after run, peak TIME_WAIT fell from 16,085 to 44 and
    failures to zero, while the raw-connection control (no application code, a new connection
    every iteration) **still failed** on the same machine (6,972 and 7,844 failed attempts in two
    of its three phases). The
    machine's limit did not change; the app stopped hitting it.
  - Every phase runs once and is reported as measured, in order (lock, no lock, lock again),
    with failures beside the successes. Nothing is retried or discarded. Requests/s counts
    successful requests only.

## Limitations

- One laptop, one run per size; Docker Desktop on macOS runs the databases in a Linux VM, so
  host-to-container networking is slower than in production and the app, load generator and
  databases compete for the same CPU cores.
- Synthetic data with an invented distribution; real postings cluster differently (skills,
  roles and locations are correlated). Mongo documents are small (no real job-description text).
- PostgreSQL and MongoDB run with default settings and a warm cache (all data fits in memory);
  cold-cache and larger-than-memory behaviour is not measured.
- Fixed random seed, so datasets are identical between runs; timings are not (they vary by a
  few tens of percent between runs).
- The throughput case uses unsigned development tokens (token verification is skipped);
  production auth adds a little CPU per request.
- No concurrent writers in the throughput case. Before connection reuse (the 2026-10-26 run) the
  throughput numbers were partly a measurement of connection set-up cost and of the host's
  outgoing-port limit (see the Finding above). Throughput has swung by up to about 2x between
  runs on this laptop.
