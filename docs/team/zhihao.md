# Zhihao — moderator, final reviewer and integration

> **Current work (PRD v2, 25 Oct 2026):** WP-0 (dev proxy + shared read lock), WP-10 (benchmark, with Jason), WP-11 (manual), review of every WP PR into `dev`. Specs, allowed files and
> acceptance criteria are in [PRD.md §5](../PRD.md); shapes in [API.md](../API.md).
> Task IDs below are from the first milestone; check their progress notes before reusing them.

Read [team workflow](README.md), [PRD](../PRD.md), [API contract](../API.md),
[ERD](../erd.md) and [database setup](../DB/README.md).

## ZHI-01 — coordinate the starting baseline

- Review the two database scripts and API contract with the team. Discuss refinements
  together; Jason/Jiaxin prepare their database changes and verify their own work.
- Ensure the baseline reaches the agreed shared dev branch before teammates branch
  from it. A local uncommitted document is not available in teammates' clones.
- Confirm access continuity for the development projects Jason and Jiaxin set up.
  They own setup; you do not need to create both deployments personally.
- Confirm the early dependency order: Nasya's common UI/client interfaces unblock
  Anuska; Jason's Supabase/auth/API work enables live profile integration; Jiaxin can
  verify MongoDB independently without blocking the first SQL profile milestone.
- Own changes to shared API/PRD/ERD documents and coordinate one editor for each.

Done when: everyone can find their guide and the same contract, database targets/owners
are known, and each person has a small first task with clear dependencies.

## ZHI-02 — review focused PRs into dev

Use [the PR checklist](../pull-request-template.md). Check behaviour and evidence:

- Does the change fulfil its task acceptance criteria and match API.md exactly?
- Did the author test success, validation, retry/error and ownership where relevant?
- Are real database checks distinguished from static/unit/mock checks?
- Are schema changes reproducible, with applied scripts preserved and shared data safe?
- Are secrets and personal data absent from source/examples/logs?
- Were shared-file and dependency changes coordinated with the other developer?

Return concrete feedback to the owner when needed. Final review does not make you the
sole tester. Agents must not approve their own PRs on your behalf; follow applicable
runtime/repository merge authority when performing integration.

## ZHI-03 — demonstrate the first complete flow

After component PRs land in dev, verify with the team:
Google sign-in → create/read profile → edit name → select/remove skills → reload.
Include a returning user, an expired session and two different accounts. Run the
documented build/backend checks and confirm the real API contract before promoting
the milestone to main. No deployment or branch protection is implied by these guides.

## Progress

Initial status: guides, API contract and bootstrap scripts are prepared locally;
publication, applied database state and feature completion must be checked. Only the
starter/health flow has implementation evidence at guide creation. Append reviewed
task/PR, integration checks and next milestone notes here without duplicating everyone’s logs.

### WP-0 progress note (overnight 2026-10-26)

- Branch: `fix/wp0-dev-proxy-and-read-lock`
- Commit: `8742c4d` (build) + `67a429c` (review fix round); orchestrator re-ran checks on `67a429c`: ruff clean, pytest 58 passed / 39 skipped, disposable DB 97 passed
- Changes: recreated `frontend/vite.config.ts` (React plugin, host 127.0.0.1, port 5173,
  `/api` proxy to 127.0.0.1:8000; `vitest.config.ts` kept). Advisory lock split in
  `backend/app/sql_access.py`: `job_read_lock()` (`pg_advisory_xact_lock_shared(2003001)`)
  and `job_write_lock()` (`pg_advisory_xact_lock(2003001)`), both after
  `SET LOCAL lock_timeout = '3s'`; a timeout (55P03) maps to the existing 503
  `service_unavailable`. `job_pipeline_lock` remains as an alias of `job_read_lock`.
  Authenticated read routes use the read lock, admin write routes the write lock.
- Checks: ruff check passed; ruff format --check passed (51 files); pytest 57 passed,
  39 skipped; disposable DB script 96 passed (includes the real-Postgres shared/exclusive
  lock test); frontend `npm test` 44 passed, `npm run build` clean.
- Proxy AC: backend (no env file) + `npm run dev`, then
  `curl -sS -i http://127.0.0.1:5173/api/health` returned `HTTP/1.1 200 OK` with body
  `{"status":"ok","service":"jobless-simulator-api"}`.
- Unverified: not run against Supabase.
- Open questions: none.

#### WP-0 fix round

- Added `get_admin_job_read_db` / `AdminJobReadDatabase` in `backend/app/dependencies.py`: admin
  authorization first, then the shared read lock.
- Open question for Zhihao: `GET /api/jobs/duplicates` (`backend/app/jobs_duplicates.py:117`) is
  read-only but still uses the exclusive `AdminJobDatabase` (that file is outside WP-0). One-line
  fix: change its parameter to `db: AdminJobReadDatabase` and import `AdminJobReadDatabase`
  instead of `AdminJobDatabase` from `.dependencies` (keep the import for `delete_duplicates`).
- Route-wiring test now enumerates every job route (jobs, search, duplicates, external multi,
  extraction); the duplicates preview is a listed known exception. Mutating fetch-multi to the
  read dependency made the test fail (verified, then restored).

### WP-0 follow-up: duplicates preview takes the shared lock (2026-10-26)

- Branch: `fix/duplicates-read-lock` (on `fix/wp0-dev-proxy-and-read-lock`), approved by Zhihao.
- `GET /api/jobs/duplicates` now uses `AdminJobReadDatabase` (admin auth + shared lock), so
  it no longer blocks student reads. `DELETE /api/jobs/duplicates` keeps the exclusive lock.
- The route-wiring test's known exception is removed; it now asserts the duplicates GET is
  covered and fails on the old dependency.
- Checks: ruff and format clean; pytest `58 passed, 39 skipped`; disposable DB `97 passed`.
