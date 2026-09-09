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
