# Working with your coding agent

The first milestone (sign-in, profile, confirmed skills) is done. Current work is
**PRD v2** ([PRD.md](../PRD.md)): work packages WP-0 to WP-11, each with an owner, branch
name, allowed files and acceptance criteria. Agents pick one WP at a time and follow
PRD §6 "Rules for coding agents".

## Start here

Tell your agent your name and what you want:

> I'm Jason. Read AGENTS.md, my team guide and docs/PRD.md, inspect the current code,
> and tell me my next unfinished work package and anything I need from another teammate.

When ready to build:

> Implement WP-2 from docs/PRD.md on a task branch. Preserve other people's work,
> run the relevant checks, and report what remains unverified.

Identity alone does not authorize implementation or external changes. If work requires
a deployment/account, confirm the exact development target and available access first.
Members own configuring their respective databases; this does not require sharing
passwords. Give Zhihao appropriate project access where supported so the team is not
dependent on one private account. Discuss costs before selecting a paid resource.

## Required reading

All members: [setup](../README.md), [PRD](../PRD.md), [API contract](../API.md),
and their individual guide. Backend members also read [ERD](../erd.md) and
[database setup](../DB/README.md). Read relevant source and tests before changing them.

## Current state — verify rather than assume

As of 25 October 2026 (`dev` @ 5dedfcb), see PRD §3 for the full list:

- Built: Google sign-in, profile and confirmed skills on PostgreSQL, resume upload to
  MongoDB, job ingestion pipeline, job read routes, `SkillEditor` component (not mounted).
- Not built: tracker, Discover ranking, skill gap, Discover/Vault/Skill Gap screens,
  resume-to-skills flow, migration 003, benchmark, user manual.
- File presence is not proof that a database was changed or a task finished.

At each new session inspect `git status`, current branch, relevant code/tests and the
latest guide notes. Compare actual behaviour to acceptance criteria. Do not overwrite
implemented work because a checkbox is stale. Update only your guide's progress notes
with your task ID, result, test command/result, PR/commit if available and remaining work.
Never record credentials, tokens, real resume content or secret connection strings.

## Ownership

| Person | Guide | Current responsibility |
|---|---|---|
| Zhihao | [zhihao.md](zhihao.md) | Scope, shared contracts, final review and integration |
| Jason | [jason.md](jason.md) | Supabase/PostgreSQL, Google provider setup, Python auth and profile/skill API |
| Jiaxin | [jiaxin.md](jiaxin.md) | MongoDB deployment, validation/index verification, backend document access |
| Nasya | [nasya.md](nasya.md) | Google sign-in UI, session/API client, onboarding/profile screen |
| Anuska | [anuska.md](anuska.md) | Skill search/add/remove component and mock scenarios |

PRD v2 work packages (contracts are in [API.md](../API.md)):

| Person | Work packages |
|---|---|
| Zhihao | WP-0 dev proxy + read lock, WP-10 benchmark (with Jason), WP-11 manual edit, all reviews |
| Jason | WP-1 SQL migration 003, WP-2 tracker API, WP-3 Discover API, WP-6 resume backend |
| Jiaxin | WP-4 MongoDB skill gap, WP-5 ingestion improvements + live ingestion run |
| Nasya | WP-7 Discover screen, app shell wiring (`App.tsx` imports) |
| Anushka | WP-6 resume/skills UI, WP-8 Vault screen, WP-9 Skill Gap screen |

### Shared files — one integrator per area

| Files/area | Integrator | Rule |
|---|---|---|
| frontend/src/App.tsx, main.tsx, style.css | Nasya | Anuska supplies components and local styles without editing the app shell |
| frontend/package.json, package-lock.json, Vite/TS config | Nasya | Agree required packages with Anuska before a focused dependency PR |
| frontend/src/lib/api.ts, types.ts, supabase.ts (planned) | Nasya | Shared API transport/types; match API.md and agree exports before both depend on them |
| backend/app/main.py, config.py, auth.py (planned) | Jason | Jiaxin supplies separate modules; Jason wires shared entry points |
| backend/pyproject.toml, uv.lock, .env.example | Jason | Jiaxin requests MongoDB/config additions through a focused shared change |
| docs/DB/*.sql | Jason | Do not edit an already-applied script; use the next SQL migration number |
| docs/DB/*collections*.js and future MongoDB scripts | Jiaxin | Do not edit applied bootstrap; use the next MongoDB change number |
| docs/API.md, erd.md, PRD.md, DB/README.md, CI, AGENTS.md | Zhihao | Review proposed changes together, with one editor for each change |

Ownership is a coordination convention, not a filesystem permission. If another owner
needs a change, describe the needed interface/change in the task or PR before both edit.
Small dependency/config PRs should land first, then both members update their branches.

## Branches and integration

Use a short-lived branch from up-to-date `dev` for each task (for example
`feat/jason-profile-api`). Check for local edits before switching and never discard them.
If `dev` or remote access is unavailable, report that instead of inventing a base.
Avoid personal branches that accumulate a semester of unrelated work.

Record tests, schema/contract impact and dependencies using the
[PR checklist](../pull-request-template.md). Zhihao reviews changes into dev, then moves
verified milestones to main. A coding agent follows its own applicable authority rules;
the guide does not automatically authorize pushing, posting a PR or merging.

## Integration boundaries to agree early

- Jason and Nasya agree the development Supabase project, browser redirect URL(s) and
  token handling before live Google sign-in. Public auth configuration may be shared;
  secret backend keys never belong in frontend variables.
- Nasya owns the common API transport: relative paths, bearer token, error envelope,
  one bounded refresh/retry on 401 and empty-body handling for 204. Anuska uses it.
- Nasya and Anuska agree the skill-editor interface before editing the shell. Initial
  target: receive confirmed skills and an async reload callback; display selected
  skills and request GET /api/me again after a successful add/remove.
- Jason owns Python token verification; Jiaxin does not build a second auth module.
  MongoDB work can be verified independently using synthetic data while SQL API work proceeds.

Each developer writes and verifies their own work. Zhihao's final review does not
replace those checks. Use [the documented commands](../README.md#checks-before-a-pull-request)
and add behavioural tests for the features you implement.
