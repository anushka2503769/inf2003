# Jason — Supabase and Python profile API

Read [team workflow](README.md), [API contract](../API.md), [ERD](../erd.md) and
[database instructions](../DB/README.md) first. Own SQL and backend auth/profile/skills;
Jiaxin owns MongoDB. Coordinate Google provider setup with Nasya.

## JAS-01 — prepare and verify Supabase development storage

- Inspect `../DB/001_initial_schema.sql` relative to this guide and the agreed schema.
- Select/configure the intended team development project using the available account
  and explicitly authorized target. Avoid paid choices without team agreement.
- Arrange appropriate project access for Zhihao; keep credentials out of Git and chat.
- Coordinate Google sign-in configuration and redirect URLs with Nasya. Google/provider
  account access is a setup dependency, not something to guess or bypass.
- Review/apply the SQL bootstrap once; inspect existing objects first. Follow its stop
  conditions. Preserve applied files; subsequent schema changes use a new SQL script.
- Add a small repeatable synthetic skill seed script under docs/DB/. Look up generated
  skill IDs by canonical name; examples in API.md are not guaranteed live IDs.

Done when: all six tables/constraints/indexes are verified; duplicate skills and links,
unknown FKs and invalid statuses are rejected; browser roles cannot access application
tables. Record which commit was applied and which checks actually ran. Clean up only
your own synthetic records, never reset the shared database.

## JAS-02 — backend foundation for authenticated requests

Planned owned files: backend/app/config.py, auth.py, SQL access module, errors.py,
matching backend/tests/ files; backend/app/main.py for integration.

- Agree the backend database access method and required configuration with the team.
  Preserve transaction requirements in API.md; do not emulate atomic operations with
  independent remote calls that can partially succeed.
- Verify Supabase tokens; derive identity from verified claims. Implement the specified
  401/503 distinction and the common error shape, with no leaked secrets/exceptions.
- Add dependencies/settings in one focused change; coordinate Jiaxin's MongoDB needs
  before editing pyproject.toml, uv.lock and .env.example simultaneously.

Done when: valid/invalid/expired token cases are tested, outage errors are distinct from
invalid credentials, and personal-data operations cannot accept a forged user_id.

## JAS-03 — implement all six first-milestone API routes

Planned owned modules: backend/app/profile.py, skills.py and matching tests.
Read exact requests/responses in API.md; don't invent alternative names or wrappers.

- Implement onboarding, GET/PATCH profile, skill lookup and PUT/DELETE membership.
- Verify concurrent/repeated onboarding and idempotent membership changes.
- Enforce ownership for every query when privileged backend credentials bypass RLS.
- Verify timestamps, 204 handling, validation errors and literal bounded search.
- Publish matching FastAPI OpenAPI definitions; supply Nasya/Anuska with live test
  readiness and limitations without exposing keys.

Done when: API.md acceptance cases pass and the frontend flow succeeds against real
Python routes. Health endpoint tests alone are not sufficient.

## Boundaries and progress

Do not implement MongoDB collections, extraction or frontend screens. Future job/tracker
routes need a separate contract. Shared documents/config changes follow team ownership.

Initial status: JAS-01/02/03 not verified complete; the SQL file exists, but no deployed
database or application route implementation has been verified. Inspect current state
before starting. Append concise task/result/check/PR/next-step notes here as work lands.

### 19 September 2026 — JAS-01, JAS-02 and JAS-03

Branch `jason/seedskills` at `2d4f651`, five commits ahead of `dev` (`8bdcb82`).
Backend checks on that branch: `ruff check` and `ruff format --check` clean,
`pytest` 46 passed and 37 skipped. The skips are the database-backed tests,
which need `TEST_DATABASE_URL`; CI runs without it, so they skip there too.

**JAS-01.** Supabase development project created in the team organization
(free tier, Singapore). The Data API is left disabled: the browser uses Supabase
for authentication only, and `001` revokes the application tables from `anon`
and `authenticated`, so PostgREST would serve nothing. "Automatically expose new
tables" is off; automatic RLS on new tables is on.

`docs/DB/001_initial_schema.sql` at commit `1de3a3b` applied once in the SQL
Editor, then verified by a scripted check returning nine results, all PASS: the
six tables exist; RLS is enabled on all six; `anon` and `authenticated` hold no
table privileges; `service_role` has full CRUD; a case-insensitive duplicate
skill name, an untrimmed skill name, a `user_skills` link to an unknown user, an
invalid `user_jobs` status with unknown foreign keys, and an invalid `job_type`
are each rejected. The probe rows that check inserted were deleted by the same
script.

`docs/DB/002_seed_skills.sql` adds 139 canonical skill names across the twelve
categories used by the fallback list in `backend/app/skills_repository.py`, so
keyword matching keeps working once that fallback is removed. No `skill_id`
values are supplied; `ON CONFLICT (lower(name)) DO NOTHING` makes re-runs safe.
Applied to the development project and run twice: 139 rows both times, no
duplicate `lower(name)`. Re-running consumes identity values for skipped rows,
so `skill_id` gaps are expected and nothing may hardcode an ID.

**JAS-02.** `backend/app/sql_profile.py` adds `PostgresProfileStore`,
implementing the existing `ProfileStore` protocol so no route handler changed.
It follows the connection idiom in `sql_access.py`: one operation opens one
connection, works on one cursor in one transaction, commits once and closes in a
finally block. `upsert` uses `INSERT ... ON CONFLICT (user_id) DO UPDATE`, with
`created_at` absent from the update so a retried onboarding neither duplicates
the row nor resets its creation time. `update_name` moves `updated_at` only when
the stored name changes. psycopg2 errors become `SqlAccessError`, which
`errors.py` maps to the 503 `service_unavailable` envelope, keeping an outage
distinct from an invalid credential.

`get_profile_store` selects PostgreSQL when `DATABASE_URL` is set and falls back
to the in-memory store with a warning otherwise, so a teammate without
credentials still runs the app; production refuses to start without it, because
silently keeping profiles in memory would look healthy and lose them on restart.

`config.py`'s module docstring claimed `uv run` populates the environment from
`backend/.env`. It does not, and `docs/README.md` already passes `--env-file`;
the docstring now states the actual mechanism. `backend/.env.example` documents
`TEST_DATABASE_URL` and what `DATABASE_URL` now holds.

**JAS-03.** All six first-milestone routes now exist.
`GET /api/skills` searches the shared dictionary with a literal substring: `%`
and `_` are escaped with `ESCAPE`, results are ordered by `lower(name)` then
`skill_id`, one row beyond the limit decides `has_more`, and unknown query
parameters are rejected with 422 rather than ignored.
`PUT` and `DELETE /api/me/skills/{skill_id}` answer 204 with no body for both
the changed and the already-in-that-state cases. Each is one function, one
connection and one transaction, so the existence checks, the membership change
and the `users.updated_at` bump cannot be split across partially succeeding
calls. A repeat that changes nothing leaves `updated_at` alone. `DELETE` removes
only the student's own link and never the shared dictionary entry.

`MeResponse` gained a `skills` array, always present and empty for a new
student, because the skill editor re-reads `GET /api/me` after each change.
404 responses carry `details.resource` ("profile" or "skill") so the frontend can
tell the two apart without a new top-level error code; the lowercase codes the
frontend already branches on are unchanged.

**Tests.** `tests/test_sql_profile.py` covers onboarding, retry, rename, the
no-op rename, account isolation, the `auth.users` foreign key, eight
simultaneous first logins producing one row, and a second writer blocking on an
uncommitted competing insert. `tests/test_skills.py` drives the HTTP routes:
ordering, case-insensitivity, literal wildcards, `has_more`, validation,
idempotency, `updated_at` handling, and that one student cannot read or change
another's skills. Both were checked against a scratch PostgreSQL 16 instance
with `001` applied. They skip unless `TEST_DATABASE_URL` is set, deliberately a
different variable from `DATABASE_URL` so a normal `backend/.env` cannot
truncate real data.

**Not yet verified.** Every auth test uses synthetic HS256 keys or the
development bypass. The ES256/JWKS path the live project actually issues has
never been exercised, so no route has been reached with a real Supabase token.
That is the remaining evidence for JAS-02 and JAS-03, and it needs Google
sign-in configured first.

**Remaining and who it needs.**

- Open the pull request for `jason/seedskills` into `dev`; Zhihao reviews.
- Google provider and redirect URL configuration with Nasya
  (`http://127.0.0.1:5173/auth/callback`, per `frontend/src/app/routes.ts`).
- Nasya adds the `skills` field to `frontend/src/types/api.ts`.
- Jiaxin can remove the fallback skill list in `backend/app/skills_repository.py`
  now that the dictionary is seeded.
- Zhihao: `docs/API.md` differs from the shipped code in five places (response
  wrapper, POST status code, error code casing, name length, and whether POST
  overwrites an existing name), plus the `details.resource` convention; and
  `docs/DB/README.md` needs a line documenting `002`.
- Confirm Zhihao has access to the Supabase project.
