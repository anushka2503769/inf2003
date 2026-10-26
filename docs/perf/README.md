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

These are readings of `results-2026-10-26.md`; re-run before quoting new numbers.

- **The MongoDB `role_category` index is the clear win.** A rare role (about 1% of documents)
  is about 3x faster at 5,000 documents (0.42 vs 1.22 ms) and about 10x at 50,000 (1.1 vs 10.7
  ms); the plan changes from COLLSCAN (every document examined) to IXSCAN (only matches). A
  common role (about 30% of documents) gains only 1.2-1.4x because most documents match anyway.
- **The Discover partial indexes barely matter at these sizes.** They turn the `jobs` Seq Scan
  into a Bitmap Index Scan (see the plan excerpt), but the statement's cost is dominated by
  joining and ranking `job_skills` for every candidate job, which no index on `jobs` removes.
  Medians are within about 10% for no filter and broad filters, and about 1.1-1.3x better for
  the selective filter, both sizes, with the two "with" phases agreeing. `jobs_active_posted_at_idx`
  is not used by Discover at all (its ORDER BY starts with the computed coverage).
- **The tracker `(user_id, status)` index does nothing measurable here.** Users have at most 50
  tracker rows (and the heavy user 2,000), and the primary key `(user_id, job_id)` already finds
  a user's rows directly; the status filter then discards a handful. All variants are "about
  the same" or within phase-to-phase noise, at both sizes. An earlier draft of this analysis
  claimed a 1.6-1.9x gain at 50,000 jobs; that came from refreshing planner statistics at the
  same moment the index was dropped, and disappeared once the methodology was fixed.
- **SQL vs MongoDB for skill gap.** At 5,000 jobs the engines are close for the common role
  (Mongo aggregation alone 15 ms, `skill_gap_sql` 18 ms, end to end both about 24-26 ms). At
  50,000 jobs `skill_gap_sql` with the role's ids known is about 1.9x (SE role, 98 vs 184 ms)
  to 1.8x (rare role, 14.7 vs 26.3 ms) faster than the Mongo aggregation, because it joins
  narrow indexed rows instead of unwinding and regrouping documents. But SQL needs the role's
  job ids, which only Mongo stores, so the fair end-to-end comparison for the design as built is
  `skill_gap_mongo` 192 ms vs SQL end to end 138 ms for the common role, and 32 vs 35 ms for the
  rare role (roughly equal). Mongo's path also returns `minimum_years`, which SQL cannot.
- **The shared read lock costs throughput, by an amount this laptop cannot pin down.** In the
  committed run the lock phases sustained 111 and 134 requests/s (median 83 and 72 ms) and the
  no-lock phase 135 requests/s (median 69 ms), so the lock cost between 0% and 18%, within the
  phase-to-phase drift. Earlier runs on the same machine measured 250-285 requests/s without the
  lock against 100-155 with it (a 40-45% cost). Quote a range ("the lock costs roughly 20-45% of
  Discover throughput locally"), not one number. The mechanism is certain even if the size is
  not: the lock is a second PostgreSQL connection per request, and the app opens a fresh
  connection per call (no pool), so the lock path makes twice as many connection set-ups. The
  benchmark has no concurrent writer, so it measures the lock's overhead, not its benefit
  (blocking readers while an admin refresh rewrites jobs); say so in the report.
- **Finding: the HTTP 503 responses seen in some with-lock phases are a connection-path
  artefact, not an application defect.** Evidence, from the diagnostics the benchmark now
  records:
  - The server-side cause chain of every 503 was `ApiError <- SqlAccessError("SQL job
    synchronization is unavailable") <- psycopg2.OperationalError: connection to server at
    "127.0.0.1", port N failed: server closed the connection unexpectedly`: the lock's own
    connection attempt failed. It was not a lock timeout (that is SQLSTATE 55P03 and would be
    "busy"), not `too many clients` (PostgreSQL never saw more than 21 sessions against
    `max_connections` 100), and PostgreSQL's own log (inspected with `BENCH_DOCKER_LOGS=1`)
    recorded no rejected connection.
  - The failures come in bursts at the start of a phase (the first 1-3 s) and never in the
    no-lock phases of the same runs, which open one connection per request.
  - The control experiment (a table in the results file) reproduces them with **no
    application code at all**: 10 threads opening raw `psycopg2` connections in a loop. In the
    committed run the nested pattern (hold one connection while opening a second, as the lock
    does) failed on about 96% and 63% of connection attempts in its two phases; the one-connection
    pattern failed on about 33% of attempts, all in the last 3.5 s of the phase. A separate
    5-worker control failed in the same way, so it is not specific to 10 workers. The
    sampler that counts PostgreSQL sessions also failed to connect during these windows.
  - Conclusion: Docker Desktop's published-port path (or, if you run this inside a sandboxed
    session, that sandbox) intermittently drops new connections under rapid connection churn.
    I could not run outside the sandboxed session used for the committed run, so I could not tell
    those two apart; re-running on an unsandboxed machine would settle it. The host-side TIME_WAIT
    count was not measurable in that session (`netstat` is blocked), so the earlier suggestion of
    ephemeral-port exhaustion is **not supported** by evidence and is withdrawn.
  - What the benchmark does about it: a phase with more than 1% failed requests is discarded and
    repeated (up to 3 attempts, cooldown between), and the table lists every attempt's failure
    count. In the committed run the first with-lock attempt failed 2,346 requests and was
    discarded; the reported phase is clean.
  - Application-side implication, worth one sentence in the report: because every request
    opens one to two brand-new PostgreSQL connections, the API is sensitive to connection-setup
    failures and pays their cost on every call. A small connection pool (for example
    `psycopg2.pool.ThreadedConnectionPool`) would remove most of the connection churn, and the
    lock connection could reuse the request's own connection. That change belongs in
    `backend/app/` and is deliberately not made here.

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
  throughput numbers are partly a measurement of connection set-up cost and of how reliably
  the Docker/host connection path accepts new connections (see the Finding above). Throughput
  swings by up to about 2x between runs on this laptop.
