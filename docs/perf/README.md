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
exit (also on Ctrl-C or failure). It uses port 8231 for the throughput server and never reads
any `.env` file. `seed_synthetic.py` and `benchmark.py` refuse any database URL whose host is
not `127.0.0.1` or `localhost`.

Files: `backend/scripts/seed_synthetic.py` (data), `backend/scripts/benchmark.py` (cases and
report), `backend/scripts/bench_server.py` (local server for the throughput case),
`backend/tests/test_benchmark_helpers.py` (localhost guard, percentile maths, seed shape).

## What each case measures

Each row is 3 warm-up calls, then 30 timed calls; the table shows the median and p95 in ms.
The code under test is the real backend code; only database objects (indexes) are toggled from
the benchmark, and in case 5 the lock is swapped for a no-op in `bench_server.py` (no file under
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
- The "With vs without" table gives the median ratio. Treat differences under about 20% as
  noise on a laptop: re-running the benchmark moves them. The EXPLAIN excerpts show what the
  planner actually did, which is the more reliable evidence than the ratio.
- Sizes: the primary run is 5,000 jobs (the PRD size); a 50,000-job run shows how the numbers
  scale. Row counts are in each section.
- Seed distribution: 8 role categories (the rarest, "Quantum Computing", is about 1%); job
  type 70/10/20% full-time/part-time/internship; work arrangement 50/30/20% onsite/hybrid/
  remote; skill popularity is Zipf-like; 5% of jobs are inactive; a requirement is REQUIRED
  60% of the time.

## What the committed run showed (2026-10-26, for the report author)

These are readings of `results-2026-10-26.md`; re-run before quoting new numbers.

- **Indexes help where the scan is the cost, and are not the whole story.** The Mongo
  `role_category` index is the clearest win: a rare role is about 4x faster at 5,000 documents
  and about 8x at 50,000 (the plan changes from COLLSCAN examining every document to an IXSCAN
  examining only matches); a common role (about 30% of documents) gains little because most
  documents match anyway. The Discover partial indexes turn the `jobs` Seq Scan into a Bitmap
  Index Scan, but the 5,000-job gain is small (about 1.1-1.5x) because the cost of the Discover
  statement is dominated by joining and ranking `job_skills` for every candidate job, which no
  index on `jobs` can avoid. `jobs_active_posted_at_idx` is not used by Discover at all (its
  ORDER BY starts with the computed coverage, not the posting date).
- **The tracker `(user_id, status)` index shows no benefit at the specified scale.** Users have
  at most 50 tracker rows, and the primary key `(user_id, job_id)` already finds a user's rows
  directly; the status filter then discards a handful of rows. Even for the 2,000-row heavy
  user at 5,000 jobs the planner's choice makes no measurable difference. Differences of about
  10% either way at 5,000 jobs are noise. At 50,000 jobs the index measured about 1.6-1.9x
  faster, but the same query is dominated by a Seq Scan on `jobs`, so read the planner output
  before claiming a mechanism.
- **SQL vs Mongo for skill gap.** At 5,000 jobs the two engines are within noise of each other
  for the common role; Mongo's aggregation alone is fast, and the SQL path is cheaper once the
  role's job ids are known. At 50,000 jobs SQL (`skill_gap_sql` with ids known) was about
  1.9-2x faster than the Mongo aggregation for both roles, because it joins narrow indexed
  rows instead of unwinding and regrouping documents. Choosing SQL for the counts needs the
  role's job ids, which only Mongo stores, so the "end to end" row is the fair comparison for
  the design as built: the engines are close there. The Mongo path also returns
  `minimum_years`, which SQL cannot.
- **The shared read lock costs throughput in this setup.** Without it the server sustained
  about 170 requests/s vs about 100 requests/s with it (median latency about 55 ms vs 84 ms).
  The lock is a second PostgreSQL connection per request (opened, locked, held for the request),
  which doubles connection set-up; there is no connection pool. The benchmark has no concurrent
  writer, so it measures the lock's overhead, not its benefit (blocking readers while an
  admin refresh rewrites jobs). Say so in the report.

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
- No concurrent writers in the throughput case.
