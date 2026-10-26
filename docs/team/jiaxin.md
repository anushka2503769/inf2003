# Jiaxin — MongoDB and document access

> **Current work (PRD v2, 25 Oct 2026):** WP-4 (MongoDB skill gap + Mongo integration tests), WP-5 (ingestion columns, skip-and-continue, CLI) and the live ingestion run. Specs, allowed files and
> acceptance criteria are in [PRD.md §5](../PRD.md); shapes in [API.md](../API.md).
> Task IDs below are from the first milestone; check their progress notes before reusing them.

Read [team workflow](README.md), [PRD](../PRD.md), [ERD](../erd.md),
[MongoDB setup](../DB/README.md#mongodb) and the [API contract](../API.md).
Own MongoDB deployment/document work. Jason owns shared Python auth and SQL access.

## JIA-01 — prepare and verify MongoDB development storage

- Select/configure the intended team development deployment using the available account
  and explicit target authorization. Discuss costs before choosing a paid resource.
- Arrange appropriate project access for Zhihao and a database user scoped to the
  application database. Keep credentials outside Git; document names, not secret values.
- Review/apply docs/DB/001_initial_collections.js according to DB/README.md. It is not
  atomic; inspect and repair partial setup rather than dropping existing collections.
- Verify validators and unique reference indexes using synthetic records: valid insert,
  duplicate user/job reference, missing/wrong field types and resume replacement.
- Use isolated synthetic IDs and remove only your own fixtures. Test parent-reference
  handling separately: MongoDB itself cannot prove SQL IDs exist.

Done when: both collections, validators and indexes are inspected on the intended
deployment, checks are recorded and current-resume replacement is demonstrated.

## JIA-02 — minimal Python MongoDB access

Planned owned files: backend/app/documents.py and backend/tests/test_documents.py.

- Coordinate driver/config additions with Jason before changing backend shared files.
  Keep one settings/auth implementation. Agree the document-module call signatures with
  Jason before another feature depends on them.
- Implement only current-resume and current-job document read/write operations needed
  by the skeleton, with predictable missing-document behaviour and explicit database selection.
- Test BSON date/ID handling, duplicate protection, replacement and error behaviour.
  Unit fixtures can run without the SQL API. Live tests must be explicitly selected
  and must not reset a shared database.

Done when: the access module can be tested independently, failures are surfaced clearly,
and no real credentials/resumes are in fixtures or logs. No public document endpoints
are implied; the first profile/skill milestone does not yet depend on MongoDB.

## Later work — discuss before implementation

Resume upload/extraction, JD processing and role-gap aggregation belong here later.
They need contracts, provider selection and normalization/SQL consistency decisions.
Do not choose an LLM/job provider, invent endpoints or start a background-worker system
as part of JIA-01/02. Raise ambiguities in validators for team review.

## Progress

Initial status: JIA-01/02 not verified complete. The bootstrap has syntax/simulated-shell
checks only; no deployment, live enforcement or Python document module is verified.
Inspect current code before work. Append task/result/check/PR/next-step notes here.

### WP-4 progress note (overnight 2026-10-26)

- Branch: `feat/wp4-skill-gap` (from `origin/dev` @ 7e813dd). Commit: `4aaa6c6` (build) + `9aaf52b` (review fix round); orchestrator re-ran checks on `9aaf52b`: ruff clean, pytest 73 passed / 56 skipped, disposable DB 128 passed / 1 xfailed
- Built: `GET /api/skill-gap/roles` and `GET /api/me/skill-gap` (API.md §8) in
  `backend/app/skill_gap.py` + `backend/app/routers/skill_gap.py`; Mongo `$match` →
  `$facet` (`$count` / `$unwind` → `$group` per job → `$group` per skill → `$sort`)
  engine and `skill_gap_sql(role_ids, user_id)` over `job_skills` (not a route; for WP-10).
  Both routes use the existing `AuthenticatedJobDatabase` read dependency (the job read lock).
- Tests: `backend/tests/test_skill_gap.py` (route contract with fakes) and
  `backend/tests/test_skill_gap_db.py` (disposable Postgres + `mongo:7`, production
  validators from `docs/DB/001_initial_collections.js` loaded by the script).
- `backend/scripts/run_disposable_db_tests.sh` now also starts a disposable `mongo:7`
  container and passes `TEST_MONGODB_URI` (WP-1 edits the same script; merge by hand).
- Checks: `ruff check` → All checks passed; `ruff format --check` → 55 files already
  formatted; `pytest` (no env) → 71 passed, 55 skipped; `run_disposable_db_tests.sh` →
  126 passed; `docker ps -a --filter name=inf2003` empty afterwards.
- Unverified: not run against the team's Supabase or MongoDB; no live ingested data.
  The SQL engine has no `minimum_years` column, so it reports years as null/0.
- Open questions: `sql_access._replace_job_skills` keeps the LAST requirement type when a
  job lists a skill twice, while PRD §4 says REQUIRED wins. It is latent today (extraction
  emits at most one requirement per skill_id) and `sql_access.py` is outside WP-4's files.
  Pinned by the strict xfail `test_skill_gap_db.py::test_engines_agree_when_links_come_from_production_sync`,
  which syncs links through `replace_job_skills`. Suggested one-line fix (table
  `public.job_skills`, columns verified): `ON CONFLICT (job_id, skill_id) DO UPDATE SET
  requirement_type = CASE WHEN job_skills.requirement_type = 'REQUIRED' THEN 'REQUIRED'
  ELSE EXCLUDED.requirement_type END`. When fixed, the xfail turns into XPASS (strict) and
  the marker must be removed. `test_engines_agree_on_normalised_job_skills_links` checks
  parity on pre-normalised links only.
  Mongo skill ids missing from the SQL dictionary are dropped from the response.
- Read lock: both routes use `AuthenticatedJobDatabase` (`get_authenticated_job_db`), still
  the exclusive try-lock on this base; WP-0 is merged first and makes it shared.
  `test_skill_gap.py::test_skill_gap_routes_use_the_job_read_dependency` asserts both routes
  use the same dependency set as the job read routes. WP-0's own route-wiring test lists
  router modules explicitly; add `skill_gap` there after the merge.
- File list: `backend/tests/test_skill_gap_db.py` is not in the PRD WP-4 list; the
  orchestrator explicitly allowed splitting the Mongo integration tests into it.
- Fix round checks: `ruff check` → All checks passed; `ruff format --check` → 55 files
  already formatted; `pytest` (no env) → 73 passed, 56 skipped;
  `run_disposable_db_tests.sh` → 128 passed, 1 xfailed, exit 0; no leftover containers.

### Follow-up: REQUIRED wins in job_skills (2026-10-26)

- Branch: `fix/job-skills-required-wins` (on `feat/wp4-skill-gap`), approved by Zhihao. SQL review: Jason.
- Resolves the question above. `_replace_job_skills` now keeps REQUIRED when a skill appears
  twice for one job (`ON CONFLICT ... SET requirement_type = CASE WHEN job_skills.requirement_type
  = 'REQUIRED' THEN 'REQUIRED' ELSE EXCLUDED.requirement_type END`).
- `test_engines_agree_when_links_come_from_production_sync` is no longer xfail; it fails on the
  old line and passes with the fix.
- Checks: ruff and format clean; pytest `73 passed, 56 skipped`; disposable DB `129 passed`.
