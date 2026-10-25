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

- Branch: `feat/wp4-skill-gap` (from `origin/dev` @ 7e813dd). Commit: (filled in by orchestrator)
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
  job lists a skill twice (`ON CONFLICT ... DO UPDATE`), while the PRD rule is REQUIRED
  wins; the engines agree only if ingestion applies REQUIRED precedence (WP-5?).
  Mongo skill ids missing from the SQL dictionary are dropped from the response.
