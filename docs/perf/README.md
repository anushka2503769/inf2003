# Performance analysis (WP-10)

Measured numbers for the report and presentation: indexes on/off, MongoDB aggregation vs the
SQL implementation of the same question, and the cost of the shared read lock. Everything is
measured on throwaway local Docker databases seeded with synthetic data. The latest output is
[results-2026-10-26.md](results-2026-10-26.md).

## Run it

Prerequisites: Docker running, `uv`, and the backend dependencies resolvable (`uv` syncs them).

```bash
bash backend/scripts/run_benchmark.sh              # from the repo root; about 8-10 minutes
BENCH_SIZES=5000 bash backend/scripts/run_benchmark.sh   # primary run only, faster
BENCH_OUT=/path/to/out.md bash backend/scripts/run_benchmark.sh
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

Cases 1 and 4 have two variants. "New connection per call" is the real path (the app opens a
PostgreSQL connection per request). "Warm connection" reuses one connection, so it shows the
query cost without connection set-up; use it to judge the index, use the first to judge what a
user would feel.

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

## What the committed run showed (2026-10-26, for the report author)

These are readings of `results-2026-10-26.md`, which is the official run: produced by the team on
their own machine (Apple M5, Docker Desktop), outside any sandbox, with
`bash backend/scripts/run_benchmark.sh`. Re-run before quoting new numbers; timings vary by a few
tens of percent between runs.

- **The MongoDB `role_category` index is the clear win, and it grows with data.** A rare role
  (about 1% of documents) is about 3.6x faster at 5,000 documents (0.32 and 0.41 ms with the
  index vs 1.33 ms without) and about 9x at 50,000 (2.6 and 2.1 ms vs 21.3 ms). The plan changes
  from COLLSCAN (every document examined) to IXSCAN (only matches). A common role (about 30% of
  documents) gains only about 1.2x at 5,000 and 1.7x at 50,000, because most documents match.
- **The Discover partial indexes start to matter at 50,000 jobs.** At 5,000 jobs every variant is
  "about the same" (within 5%). At 50,000 jobs the real request path (new connection per call)
  is about 1.5x (no filter), 2.2x (broad filter) and 2.0x (selective filter) faster with the
  indexes. Treat the no-filter row with care: its two "with" phases disagree (322 vs 191 ms),
  so the size of that effect is uncertain. With a warm connection the broad filter shows no
  gain; the cost there is joining and ranking `job_skills` for every candidate job, which no
  index on `jobs` removes. `jobs_active_posted_at_idx` is not used by Discover (its ORDER BY
  starts with the computed coverage).
- **The tracker `(user_id, status)` index does nothing measurable here.** Every variant is
  "about the same" or 1.1-1.2x, which is within the gap between the two "with" phases, at both
  sizes. Users have at most 50 tracker rows (the supplementary heavy user 2,000), and the
  primary key `(user_id, job_id)` already finds a user's rows directly. An earlier draft
  claimed a 1.6-1.9x gain at 50,000 jobs; that came from refreshing planner statistics at the
  moment the index was dropped, and disappeared once the methodology was fixed.
- **SQL vs MongoDB for skill gap.** At 5,000 jobs the engines are close: common role, Mongo
  aggregation alone 14.4 ms vs `skill_gap_sql` 17.3 ms; end to end 24.0 vs 23.7 ms. At 50,000
  jobs `skill_gap_sql`, with the role's job ids known, is about 1.8x faster than the Mongo
  aggregation (common role 113 vs 209 ms, rare role 19.4 vs 35.2 ms): it joins narrow indexed
  rows instead of unwinding and regrouping documents. SQL needs the role's job ids, which only
  Mongo stores, so for the design as built the fair end-to-end comparison is close: 214 ms
  (`skill_gap_mongo`) vs 198 ms (SQL end to end) for the common role, 45.7 vs 48.0 ms for the
  rare role. Mongo's path also returns `minimum_years`, which SQL cannot.
- **The shared read lock costs about a third of Discover throughput here.** Without the lock the
  server sustained 230.6 successful requests/s (median 38 ms). With it: 143.4 and 156.4
  successful requests/s (median 51 and 54 ms), about 32-38% less. The with-lock phases also
  failed requests (see the Finding below), so they were offered more load than they served. The
  benchmark has no concurrent writer, so it measures the lock's overhead, not its benefit
  (blocking readers while an admin refresh rewrites jobs); say so in the report.
- **Finding: the lock path exhausts the host's outgoing ports under load.**
  - Both with-lock phases returned HTTP 503 `service_unavailable` (8,170 and 4,335 responses);
    the no-lock phase returned none. The server-side cause chain is `ApiError <- SqlAccessError
    <- psycopg2.OperationalError: connection to server at "127.0.0.1", port N failed: server
    closed the connection unexpectedly`: opening the lock's PostgreSQL connection failed. It is
    not a lock timeout (that would be SQLSTATE 55P03).
  - PostgreSQL was not the limit: peak sessions were 18 and 19 of `max_connections` 100, with
    full sampling coverage (30 of about 30 samples).
  - The host was: peak sockets in TIME_WAIT reached 16,085 and 14,021 in the with-lock phases
    against 7,454 without the lock, and failures began 22.6 s and 25.9 s into those phases, once
    TIME_WAIT had built up. macOS's default range of outgoing (ephemeral) ports is 16,384
    (49152-65535); check yours with `sysctl net.inet.ip.portrange.first net.inet.ip.portrange.last`.
  - Why the lock path: the app opens a fresh PostgreSQL connection per call (no pool), and the
    lock path opens a second one per request. Each closed connection holds its port in TIME_WAIT
    for a while, so twice the connection rate fills the port range within a 30-second phase.
  - The raw-connection control (no application code) shows the same: two nested connections per
    iteration failed early and often, and even one connection per iteration started failing after
    about 25 s of sustained churn.
  - What it means for the app: under sustained load the backend, not the database, runs out of
    connections to open. A small connection pool (for example
    `psycopg2.pool.ThreadedConnectionPool`), with the lock taken on the request's own connection,
    would remove most connection set-up and this failure mode. That change belongs in
    `backend/app/` and is not made here; it is a candidate improvement for the report's
    discussion section.
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
- The throughput case uses unsigned development tokens (token verification is skipped) and no
  connection pool; production auth adds a little CPU per request.
- No concurrent writers in the throughput case, and no connection pool in the app, so the
  throughput numbers are partly a measurement of connection set-up cost and of the host's
  outgoing-port limit (see the Finding above). Throughput has swung by up to about 2x between
  runs on this laptop.
