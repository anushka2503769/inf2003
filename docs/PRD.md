# Jobless Simulator — PRD v2 (build to final submission)

Status: **v2, 25 October 2026.** Supersedes the 9 September MVP baseline. The proposal
was approved ("good to go ahead with implementation"). Final submission is due
**Sunday 29 November 2026, 11:30 PM** (report, slides, video, source + user manual).

This document is written so that a coding agent can pick up one work package (WP),
build it on its own branch and prove it is done without asking anyone. Exact request
and response shapes live in [API.md](API.md); the schema lives in [erd.md](erd.md).
If this PRD and API.md disagree, API.md wins for shapes and this PRD wins for scope.

## 1. Product in one paragraph

A student signs in with Google, creates a profile, uploads a resume, confirms the skills
suggested from it, then swipes through internships and entry-level jobs ranked by how
many of the job's required skills they already have. Every decision (saved or not
interested) lands in a tracker where they move jobs through applied → interview →
offer/rejected. For any target role they can see which skills appear most often across
real postings for that role and which of those they are missing. Scores describe
**skill coverage**, never the chance of being hired.

## 2. Why the design looks like this (assessment drivers)

The module grades 25% relational and 25% NoSQL work; extra credit for views, nested and
aggregate queries, non-standard integrity constraints, analytics and a good UI. Every WP
below exists to make one of these visible in the demo and the final report:

| Assessment item | Where it is demonstrated |
|---|---|
| ER design, 1:N, M:N, data types, constraints | Six SQL tables, three junction tables, CHECK/UNIQUE/FK ([erd.md](erd.md)) |
| CRUD | Profile, confirmed skills, resume document, tracker rows (create/read/update/delete) |
| Complex SQL | Discover ranking (CTEs, aggregates, `FILTER`, window `RANK()`, anti-join), tracker summary (`GROUP BY`) |
| Views / triggers / non-standard constraints | Migration `003` (WP-1): views, `updated_at` trigger, "new tracker row needs an active job" trigger |
| NoSQL schema + validation | `$jsonSchema` validators, unique indexes on `resume_documents` / `job_documents` |
| Complex NoSQL | Skill-gap aggregation pipeline (`$match`/`$unwind`/`$group`/`$facet`), role list, stats |
| Cross-database consistency | Readiness flag + staged activation ([job-pipeline.md](job-pipeline.md)) |
| Performance analysis | WP-10 benchmark: indexes on/off, SQL vs MongoDB for the same skill-gap question |

## 3. Current state (verified on `dev` @ 5dedfcb, 25 Oct 2026)

Checks on that commit: backend `ruff` clean, `pytest` 51 passed / 38 skipped (the skipped
ones need the disposable Postgres, see §6), frontend `npm run build` clean, `npm test` 44 passed.

**Built and wired**

- Auth: Supabase Google sign-in (frontend); backend verifies JWT via JWKS/HS256 (`backend/app/auth.py`).
- Profile + confirmed skills on real PostgreSQL via psycopg2 (`sql_profile.py`, `sql_skills.py`);
  in-memory profile store only when `DATABASE_URL` is empty outside production.
- Resume upload (PDF/DOCX ≤ 5 MB) → rule-based extraction → MongoDB `resume_documents` (one per user).
- Job pipeline: providers `arbeitnow`, `devitjobs_uk`, `ai_dev_jobs` (no API keys) →
  SQL upsert by `(source, external_job_id)` → Mongo `job_documents` → `job_skills` links →
  ready → active. Rule-based skill/requirement extraction and role classification. Admin-only.
- Job read routes (list, search, stats, by id) over Mongo filtered by active SQL ids.
- Frontend: sign-in, callback, onboarding (name step), profile screen, route guards,
  `SkillEditor` component with real and mock clients (tested, **not mounted** anywhere).

**Not built (this PRD's scope)**

- Tracker (`user_jobs` table is unused by any code).
- Discover feed with skill-overlap ranking.
- Skill-gap per target role.
- Resume → suggested skills → confirmed skills flow; resume section of the profile screen.
- Discover, Vault and Skill Gap screens (placeholders in `frontend/src/screens/Placeholders.tsx`).
- `jobs.job_type`, `work_arrangement`, `location`, `source_posted_at` are never written by ingestion.
- No SQL views/triggers/functions; no MongoDB integration tests; no benchmark; no user manual.

**Known defects to fix first (WP-0)**

1. `frontend/vite.config.ts` was deleted in c5c1a39 (replaced by `vitest.config.ts`).
   The dev server no longer proxies `/api` to the backend, so the running app cannot reach Python.
2. Every job **read** takes the same exclusive `pg_try_advisory_xact_lock` as writes
   (`sql_access.job_pipeline_lock`), so two users browsing at once get 503s. Reads must not
   block each other.
3. `docs/API.md` described a stale error contract; it is rewritten in this change to match
   the code (`{error:{code,message,details?}}`, lowercase codes).

## 4. Decisions made for this build (do not reopen overnight)

These close the "still open" items of PRD v1. Change them only through Zhihao.

| Topic | Decision |
|---|---|
| Extraction | Stay **rule-based** (dictionary regex + heuristics). No LLM in this build. Report it honestly as rule-based. |
| Job provider | **Primary:** a one-off LinkedIn Singapore export via Apify (`backend/scripts/fetch_linkedin_apify.py`, 18 internship searches across tech and non-tech roles, ≤ 30 each, ≤ US$2), imported from file. **Secondary:** the three implemented keyless providers. Target 200–500 active jobs. The report must state LinkedIn data was collected once via Apify for coursework only. |
| Tracker statuses | `NOT_INTERESTED, SAVED, APPLIED, INTERVIEW, REJECTED, OFFER` (as in the SQL CHECK). |
| Swipe persistence | **One immediate `PUT` per decision** with optimistic UI and a visible retry on failure. No browser batching, no offline queue. |
| Requeue | `DELETE /api/me/jobs/{job_id}` removes a decision ("undo"), so the job can reappear in Discover. This is the tracker's D in CRUD. |
| Ranking | `coverage = matched REQUIRED / total REQUIRED`. Ties: more PREFERRED matched, then newer `source_posted_at`, then `job_id`. Jobs with zero extracted requirements have `coverage = null` and sort last with an "no requirements extracted" label. |
| Skill-gap denominator | Number of **active, ready** jobs in the chosen `role_category`. A skill counts once per job. REQUIRED wins over PREFERRED if a job lists both. |
| Experience | `minimum_years` is shown as "mentioned in N postings (max X yrs)"; never compared to the user (user years are unconfirmed). |
| Semantic matching / vectors | Out of scope. |
| Account deletion | Out of scope; FKs stay `ON DELETE RESTRICT`. |
| Deployment | Out of scope. Demo runs locally against the team's Supabase + MongoDB dev projects. |

## 5. Work packages

Each WP lists: owner (human accountable for review), branch, dependencies, files it may
touch, the build, and **acceptance criteria (AC)** that must be proven by tests or a
recorded command. Shapes referenced as "API §x" are in [API.md](API.md).

Dependency order:

```text
WP-0 ─┬─> WP-1 ──> WP-2 ──┐
      │          └> WP-3 ──┼─> WP-10 (benchmark)
      │   WP-4 (Mongo) ────┘
      │   WP-5 (ingestion) ── runs before live demo data
      │   WP-6 (resume → skills, backend)
      └─> WP-7, WP-8, WP-9, WP-6F (frontend; build against mocks, swap to real client last)
WP-11 (docs/manual) last
```

Frontend WPs never wait for backend WPs: they build against contract-exact mocks (same
pattern as `frontend/src/features/skills/mocks.ts`) and switch to the real client when
the backend WP lands on `dev`.

### WP-0 — Unblock dev server and concurrent reads (owner: Zhihao)

Branch `fix/wp0-dev-proxy-and-read-lock`. Files: `frontend/vite.config.ts`,
`frontend/vitest.config.ts`, `backend/app/sql_access.py`, `backend/app/dependencies.py`,
`backend/tests/test_jobs_pipeline.py`.

1. Recreate `frontend/vite.config.ts`: React plugin, `server: { host: '127.0.0.1', port: 5173,
   proxy: { '/api': 'http://127.0.0.1:8000' } }`. Keep `vitest.config.ts` working
   (either merge test config into `vite.config.ts` and delete `vitest.config.ts`, or keep both).
2. Split the advisory lock: reads take `pg_advisory_xact_lock_shared(2003001)`, writes take
   `pg_advisory_xact_lock(2003001)`, both after `SET LOCAL lock_timeout = '3s'`; a timeout
   maps to the existing 503 `service_unavailable`. Read dependencies use the shared variant.

AC: `npm run dev` + backend running → `GET http://127.0.0.1:5173/api/health` returns 200
(record the command output in the PR). A unit test proves read routes request the shared
lock and admin write routes the exclusive one. All existing tests still pass.

### WP-1 — SQL migration 003: views, triggers, indexes (owner: Jason)

Branch `feat/wp1-sql-003`. Files: `docs/DB/003_views_triggers_indexes.sql` (new),
`backend/scripts/run_disposable_db_tests.sh`, `backend/tests/test_sql_003.py` (new),
[erd.md](erd.md) "Migration 003" section. Do **not** edit `001`/`002`.

Contents (one transaction, idempotent-safe to *fail* if objects exist — same style as 001):

1. `set_updated_at()` trigger function; `BEFORE UPDATE` triggers on `users` and `user_jobs`
   that set `updated_at = now()` only `WHEN (OLD.* IS DISTINCT FROM NEW.*)`.
2. Non-standard constraint: trigger `user_jobs_requires_active_job` — `BEFORE INSERT` on
   `user_jobs` raises `check_violation` (SQLSTATE 23514) if the job is not `is_active`.
   Updates of existing rows for jobs that later became inactive stay allowed.
3. View `v_job_requirement_counts(job_id, required_total, preferred_total)` over `job_skills`
   joined to active jobs (aggregate with `COUNT(*) FILTER (WHERE …)`).
4. View `v_user_tracker_summary(user_id, status, job_count)`.
5. Indexes: partial `jobs (job_type, work_arrangement) WHERE is_active`, partial
   `jobs (source_posted_at DESC) WHERE is_active`, `user_jobs (user_id, status)`.
6. `REVOKE` views from `PUBLIC, anon, authenticated`; `GRANT SELECT` to `service_role`
   (match 001's access model).

Update `run_disposable_db_tests.sh` to apply `001` then `003` (still not `002`).

AC (in the disposable DB): trigger refreshes `updated_at` on a real change and not on a
no-op update; inserting `user_jobs` for an inactive job fails with 23514; updating an
existing row after the job is deactivated succeeds; both views return expected counts
for a synthetic fixture; `EXPLAIN` shows the partial index used for a filtered active-job
query. **Applying 003 to the shared Supabase project is a human step for Jason**, recorded
in [DB/README.md](DB/README.md) with date and commit.

### WP-2 — Tracker API (owner: Jason)

Branch `feat/wp2-tracker-api`. Depends on WP-1 (trigger) for the inactive-job rule; until
then the route checks `is_active` itself. Files: `backend/app/sql_tracker.py`,
`backend/app/routers/tracker.py`, `backend/app/schemas.py` (append), `backend/app/main.py`
(one `include_router` line), `backend/tests/test_tracker.py`, `backend/tests/test_tracker_sql.py`.

Routes: API §6 — `PUT /api/me/jobs/{job_id}`, `GET /api/me/jobs`, `GET /api/me/jobs/summary`,
`DELETE /api/me/jobs/{job_id}`.

- `PUT` upserts with `INSERT … ON CONFLICT (user_id, job_id) DO UPDATE SET status = EXCLUDED.status`
  in one statement; returns the tracker item. Creating a row for an unknown or inactive
  job → 404 `not_found` with `details.resource = "job"`; no profile → 404 `resource = "profile"`.
- `GET` joins `user_jobs` to `jobs`, filters by repeated `status` params, orders by
  `updated_at DESC, job_id`, paginates with `limit`/`offset`, returns `total` via `COUNT(*) OVER ()`.
- `summary` reads `v_user_tracker_summary` (or the equivalent `GROUP BY` before WP-1) and
  returns every status with 0 filled in.
- Every query filters by the verified `user_id`; no request field can name another user.
- Does **not** take the job pipeline lock.

AC: route tests with a fake store cover 200/204/404/422 and ownership; SQL tests in the
disposable DB cover idempotent repeat `PUT`, status change bumps `updated_at`, `DELETE`
twice → 204 twice, user A cannot see or change user B's rows, summary zeros.

### WP-3 — Discover feed with SQL ranking (owner: Jason; Zhihao reviews the query)

Branch `feat/wp3-discover-api`. Files: `backend/app/sql_discover.py`,
`backend/app/routers/discover.py`, schemas append, `main.py` one line,
`backend/tests/test_discover.py`, `backend/tests/test_discover_sql.py`.

Route: API §7 — `GET /api/discover`.

One SQL statement, written for readability and shown in the report:

1. CTE `candidate` — active jobs matching optional filters (`job_type`, `work_arrangement`,
   `location ILIKE` literal-escaped, `q` against title/company), **anti-join** excluding any
   `user_jobs` row for this user (`NOT EXISTS`).
2. CTE `req` — per candidate job: `required_total`, `required_matched`, `preferred_total`,
   `preferred_matched` using `COUNT(*) FILTER (…)` over `job_skills LEFT JOIN user_skills`.
3. Ranked select with `coverage = required_matched::numeric / NULLIF(required_total, 0)`,
   `RANK() OVER (ORDER BY coverage DESC NULLS LAST, preferred_matched DESC, source_posted_at DESC NULLS LAST)`,
   `ORDER BY` the same keys plus `job_id`, `LIMIT/OFFSET`.
4. Matched/missing skill lists for the returned page only, via `json_agg` in a
   `LEFT JOIN LATERAL` (or a second query for the page's job ids).

AC: deterministic order on a synthetic fixture (write the expected order in the test);
reviewed jobs never appear; filters combine with AND; a job without requirements has
`coverage: null` and sorts after all scored jobs; no profile → 404 `profile`; `limit` > 50
→ 422. `EXPLAIN ANALYZE` output for the fixture saved under `docs/perf/` for WP-10.

### WP-4 — Skill gap with MongoDB aggregation (owner: Jiaxin)

Branch `feat/wp4-skill-gap`. Files: `backend/app/skill_gap.py`, `backend/app/routers/skill_gap.py`,
schemas append, `main.py` one line, `backend/tests/test_skill_gap.py`,
`backend/scripts/run_disposable_db_tests.sh` (add a disposable `mongo:7` container and
`TEST_MONGODB_URI`; coordinate the edit with WP-1 — whoever lands second rebases).

Routes: API §8 — `GET /api/skill-gap/roles`, `GET /api/me/skill-gap?role_category=…`.

Pipeline for one role (document in code comments and the report):

1. SQL: active job ids (shared read lock).
2. Mongo `job_documents.aggregate`:
   `$match {job_id: {$in: ids}, "extracted_data.role_category": role, "extracted_data.provider.ready": "true"}`
   → `$facet`:
   - `sample`: `$count` jobs.
   - `skills`: `$unwind requirements` → `$group {_id: {job_id, skill_id}, required: {$max: is_required}, years: {$max: minimum_years}}`
     (dedupe per job) → `$group {_id: skill_id, job_count, required_count, max_years, years_mentions}` → `$sort {job_count: -1, _id: 1}`.
3. SQL: names for the returned skill ids and the user's confirmed skills; mark `user_has`.
4. Also implement `skill_gap_sql(role_ids, user_id)` — the same answer from SQL
  `job_skills` (role ids still come from Mongo) — used by WP-10 and by a test that asserts both
   engines return identical counts on the fixture. It is not exposed as a route.

`/roles` is a Mongo `$group` by `role_category` over ready documents whose `job_id` is active,
returning `{role_category, job_count}` sorted by count.

AC: Mongo integration tests (disposable container) on a synthetic fixture verify the
denominator, once-per-job counting, REQUIRED precedence, `user_has`, empty role → `sample_size: 0`
and `skills: []` (not an error), unknown role → same empty result; SQL and Mongo engines agree.

### WP-5 — Ingestion that fills SQL columns and survives bad records (owner: Jiaxin; Jason reviews SQL)

Branch `feat/wp5-ingestion`. Files: `backend/app/job_sources.py`, `backend/app/jobs_external_multi.py`,
`backend/app/sql_access.py` (upsert columns only), `backend/scripts/ingest_jobs.py` (new),
`backend/tests/test_jobs_pipeline.py`.

1. Normalizers populate `location`, `job_type` (`INTERNSHIP` if title/type mentions intern,
   else `FULL_TIME`/`PART_TIME` when stated, else null), `work_arrangement` (`REMOTE` when the
   provider flags remote, `HYBRID` when "hybrid" appears, else `ONSITE` only when stated,
   else null) and `source_posted_at`. Upsert writes them and refreshes `last_seen_at`;
   `first_seen_at` is never overwritten. Today the normalizers keep only `location`
   (defaulting to the string `"Not specified"`, which must become null) and a `remote`
   boolean (`job_sources.py:82`, `:133`, `:202`); read `job_types` / `created_at` (Arbeitnow)
   and the equivalent feed fields from the raw provider payload.
2. `fetch-multi` processes records independently: one bad record is counted and skipped,
   not fatal. Response adds `summary {requested, inserted, updated, rejected, errors[]}`
   (inserted vs updated from `xmax = 0` on the upsert's `RETURNING`).
3. `scripts/ingest_jobs.py --sources arbeitnow devitjobs_uk --limit-per-source 200` runs the
   same pipeline from the CLI using `backend/.env`, prints the summary, exits non-zero on
   total failure. Prefer internships / junior roles where the provider allows filtering.
4. **LinkedIn file source (primary demo data).** Add source `linkedin_apify` that reads a
   file produced by `backend/scripts/fetch_linkedin_apify.py` (already written, run by Zhihao):
   `ingest_jobs.py --file data/raw/linkedin_sg_<date>.json`. The file is
   `{source, actor, fetched_at, location, searches[], job_count, jobs[]}`; each job has
   `id, url, title, companyName, location, postedAt, employmentType, seniorityLevel,
   jobFunction, industries, applyUrl, descriptionText, descriptionHtml, search_keywords[]`.
   Mapping: `external_job_id = id`; `application_url = applyUrl` if http(s), else `url`;
   `company_name = companyName`; `source_posted_at = postedAt` (date, midnight UTC);
   `job_type`: `INTERNSHIP` if `employmentType == "Internship"` or the title contains
   "intern", else `FULL_TIME` / `PART_TIME` from `employmentType`, else null (Contract,
   Temporary → null); `work_arrangement` from "remote"/"hybrid"/"on-site" wording in
   location or description, else null; `raw_jd = descriptionText`. `industries` goes to the
   existing `extracted_data.industry` field. The file path never makes a network call.
   The real export (504 Singapore internships, 25 Oct 2026, ~4 MB) is **not in git**:
   `data/raw/` is ignored while the repository is public. Zhihao holds it and shares it
   via the team drive. Agents never need it: build and test only against the synthetic
   fixture. Running the importer on the real file is the human step below.
   Write the parsing tests against a small synthetic fixture with the same shape
   (`backend/tests/fixtures/linkedin_apify_sample.json`); never commit recruiter data.

AC: unit tests with recorded provider fixtures (no network) cover each normalizer field,
the LinkedIn file mapping (every rule above), the skip-and-continue behaviour and the summary counts. **Running the script against the
shared databases is a human step** (Jiaxin/Jason) and its printed summary goes in the
final report.

### WP-6 — Resume → suggested skills → confirmed skills (backend: Jason, frontend: Anushka)

Branch `feat/wp6-resume-skills`. Backend files: `backend/app/resumes.py`, `resumes_read.py`,
schemas append, tests. Frontend files: `frontend/src/features/resume/*`,
`frontend/src/screens/ProfileScreen.tsx`.

Backend (API §5):
- Upload checks the profile exists **before** extraction (404 `profile`).
- Upload response adds `suggested_skills: [{skill_id, name}]` — extracted names mapped to
  dictionary ids, minus skills the user already confirmed. Unknown names are dropped.
- New `GET /api/me/resume` returns the caller's current resume (same shape) or 404 `resume`.

Frontend:
- Profile screen "Resume and skills" section: upload control (PDF/DOCX ≤ 5 MB, client-side
  check), current resume file name + upload time, checklist of suggested skills (all
  ticked by default), "Add selected" → sequential `PUT /api/me/skills/{id}` then reload profile.
- Mount `SkillEditor` with `realSkillsClient` in the same section for manual add/remove.

AC: backend tests for ordering, mapping and 404s; frontend tests for upload validation,
suggested-skill confirm (including a failed PUT shown as not saved), and that the editor
is mounted with the real client outside tests.

### WP-7 — Discover screen (owner: Nasya)

Branch `feat/wp7-discover-ui`. Files: `frontend/src/features/discover/*` (client, real client,
mocks, types, components, css, tests), `frontend/src/screens/DiscoverScreen.tsx`,
one import change in `frontend/src/App.tsx` (replace the placeholder import).

- Filter bar: job type, work arrangement, location text, keyword; applied on submit; held in
  URL search params (not stored server-side).
- Card shows title, company, location, type/arrangement badges, posted date, a coverage bar
  with "You have X of Y required skills", matched skills (chips) and missing skills (chips,
  REQUIRED first). `coverage: null` → "No skill requirements were extracted for this job."
- Actions: **Not interested** (←), **Save** (→), **Open posting** (opens `application_url`
  in a new tab with `rel="noopener noreferrer"`). Decision = optimistic removal + `PUT`;
  on failure the card returns with an inline "Not saved — retry" message.
- Prefetch the next page when ≤ 3 cards remain. Empty state: "No more jobs for these filters"
  with "Change filters" and "Check again".
- Wording never implies hiring probability.

AC: vitest tests with mocks for render, keyboard shortcuts, optimistic remove + rollback on
error, empty state, null coverage, pagination; `npm run build` clean.

### WP-8 — Vault / tracker screen (owner: Anushka)

Branch `feat/wp8-vault-ui`. Files: `frontend/src/features/tracker/*`, `frontend/src/screens/VaultScreen.tsx`,
one import change in `App.tsx`.

- Tabs per status with counts from `GET /api/me/jobs/summary`; default tab SAVED.
- Rows: title, company, status `<select>` (change → `PUT`, optimistic with rollback),
  "Open posting", "Remove" (→ `DELETE`, confirm dialog), updated date.
- Pagination 20 per page. Empty state per tab.

AC: tests for tab counts, status change success/failure, remove, pagination, empty state.

### WP-9 — Skill Gap screen (owner: Anushka)

Branch `feat/wp9-skill-gap-ui`. Files: `frontend/src/features/skill-gap/*`,
`frontend/src/screens/SkillGapScreen.tsx`, one import change in `App.tsx`.

- Role dropdown from `/api/skill-gap/roles` (shows job counts). On select, call `/api/me/skill-gap`.
- Header: "Based on N active postings for <role>". Below 5 postings show a small-sample warning.
- Ranked horizontal bars (plain CSS/SVG, no chart library): skill name, `job_count / sample_size`
  percentage, REQUIRED/PREFERRED split, a "You have this" tick or "Gap" tag, and
  "Experience mentioned: up to X yrs (N postings)" when present.
- Summary line: "You have K of the top 10 skills for this role."
- Each gap has an "Add to my skills" shortcut only if the user actually has it (calls
  skills PUT) — no fake learning resources.

AC: tests for empty role list, zero sample, small-sample warning, has/gap marking, error state.

### WP-10 — Performance analysis (owner: Zhihao, Jason)

Branch `feat/wp10-benchmark`. Files: `backend/scripts/seed_synthetic.py`,
`backend/scripts/benchmark.py`, `docs/perf/README.md`, `docs/perf/results-<date>.md`.

- `seed_synthetic.py` fills **only a disposable database** (refuses to run unless the
  URLs point at `127.0.0.1`/`localhost`): N jobs (default 5,000), dictionary skills,
  3–12 requirements per job, 50 users with 5–20 skills and 0–50 tracker rows, matching
  Mongo documents. Fixed random seed.
- `benchmark.py` runs each case 30× after 3 warm-ups and reports median/p95:
  1. Discover query with vs without the WP-1 partial indexes (drop/recreate in the disposable DB).
  2. Skill gap: Mongo aggregation vs `skill_gap_sql` for the same role.
  3. Mongo role filter with vs without the `role_category` index.
  4. Tracker list: `(user_id, status)` index on vs off.
  5. Throughput: concurrent Discover requests (10 workers, 30 s) before and after WP-0's
     shared read lock, using `httpx` against a local server.
- Results written as a Markdown table plus `EXPLAIN (ANALYZE, BUFFERS)` / `explain("executionStats")`
  excerpts.

AC: one command reproduces the results file from a clean disposable setup; numbers are
measured, not estimated; limitations listed (local machine, synthetic distribution).

### WP-11 — User manual and report support (owner: all; Zhihao edits)

Files: `docs/USER_MANUAL.md`, `docs/README.md`, [API.md](API.md), [erd.md](erd.md).

- Manual: prerequisites, Supabase + Mongo setup (scripts 001/002/003, collections, search
  indexes), env files, running both servers, admin ingestion command, demo walkthrough,
  troubleshooting. A reader must be able to run the app from it alone.
- Regenerate the ER diagram image if the schema changed.
- Keep API.md matching FastAPI's OpenAPI output.

## 6. Rules for coding agents (apply to every WP)

1. **Branch** from up-to-date `dev` with the branch name above. One WP per branch. Never
   push to `dev` or `main`; never merge. Push your branch and open a PR to `dev` only if
   your operator allowed it; otherwise leave commits on the local branch.
2. **Shared files**: follow the ownership table in [team/README.md](team/README.md). Allowed
   edits to shared files are limited to what the WP names (e.g. one `include_router` line,
   one import in `App.tsx`, appending models to `schemas.py`).
3. **No live shared databases.** Do not connect to or write the team's Supabase or MongoDB
   projects. Use fakes for route tests and the disposable Docker databases
   (`backend/scripts/run_disposable_db_tests.sh`) for SQL/Mongo tests. Steps marked
   "human step" are left for the named person.
4. **No secrets** in code, tests, fixtures, logs or docs. Synthetic data only; no real resumes.
5. **Contracts**: implement API.md exactly. If a shape must change, change API.md in the
   same PR and say so in the PR description.
6. **Checks before calling a WP done** (paste the output tail in the PR / progress note):
   ```sh
   cd backend && uv run --locked ruff check . && uv run --locked ruff format --check . && uv run --locked pytest
   bash backend/scripts/run_disposable_db_tests.sh   # when the WP touches SQL or Mongo
   cd frontend && npm test && npm run build
   ```
7. **Progress note**: append to the owner's guide in `docs/team/<name>.md` — WP id, branch,
   commit, checks run with results, what is unverified (e.g. "not run against Supabase").
8. Match the surrounding code style: psycopg2 one-connection-per-operation pattern,
   `ApiError` for coded errors, pydantic models in `schemas.py`, feature folders with
   `client.ts` / `realClient.ts` / `mocks.ts` on the frontend.

## 7. End-to-end acceptance (before the video is recorded)

- New user: Google sign-in → name → upload synthetic resume → confirm suggested skills →
  Discover shows ranked jobs with matched/missing skills → Save two, reject one →
  Vault shows them under the right tabs → change one to APPLIED → Skill Gap for a role shows
  sample size and gaps → reload: everything persists.
- A second account sees none of the first account's skills, resume or tracker rows.
- 200+ active jobs loaded with non-null `job_type` for most rows (report the actual counts).
- Repeating ingestion creates no duplicate `(source, external_job_id)` rows.
- Benchmark results file exists and is quoted in the report.

## 8. Timeline to submission

| Dates | Milestone |
|---|---|
| 26–27 Oct | WP-0 merged; WP-1, WP-4, WP-5 backend and WP-7/8/9 against mocks in progress |
| 28 Oct–3 Nov | WP-2, WP-3, WP-6 merged; frontends switched to real clients; 003 applied; live ingestion run |
| 4–10 Nov | WP-10 benchmark; end-to-end acceptance (§7); bug fixing |
| 11–22 Nov | Report (≤ 10 pages, Calibri 12), slides (order: background → SQL → NoSQL → performance), user manual |
| 23–28 Nov | Record video (≤ 10 min, every member presents, name on screen); final zip check |
| 29 Nov 23:30 | Submit zip: report PDF, .pptx, .mp4, source + data + manual |

## 9. Non-goals

Employer portals, internal or automatic applications, resume rewriting, interview coaching,
salary or hiring predictions, LLM extraction, vector/semantic search, live or scheduled scraping
(the one-off Apify LinkedIn export in WP-5 is the only scraped source),
message queues, background workers, microservices, real-time ingestion, account deletion,
production deployment.
