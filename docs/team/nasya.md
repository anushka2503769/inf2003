# Nasya — sign-in, onboarding and profile

> **Current work (PRD v2, 25 Oct 2026):** WP-7 (Discover screen) and the `App.tsx` import swaps for the new screens. Specs, allowed files and
> acceptance criteria are in [PRD.md §5](../PRD.md); shapes in [API.md](../API.md).
> Task IDs below are from the first milestone; check their progress notes before reusing them.

Read [team workflow](README.md), [setup](../README.md), [PRD](../PRD.md) and
[API contract](../API.md). Own the frontend shell and common client modules; coordinate
skill-editor integration with Anuska and Google setup with Jason.

## NAS-01 — common frontend interfaces and session/client setup

Planned owned files: frontend/src/lib/types.ts, api.ts, supabase.ts; frontend package
manifest/lockfile; App.tsx, main.tsx and global style.css as needed.

- Agree/export Skill, Profile, SkillSearchResponse and ApiError types matching API.md.
- Agree with Anuska the shared client's exported functions and the skill-editor props
  before both depend on them. Keep JSON snake_case and handle empty 204 responses.
- Set up Google sign-in/session handling through Supabase. Coordinate the project and
  redirect URLs with Jason. Document frontend public configuration in a safe example;
  no secret or database connection string belongs in the browser.
- Implement bearer-token transport and the contract's bounded refresh/retry behaviour.
  Clear personal state and ignore late responses after logout/account changes.

Done when: shared types/interfaces are available, login/session error states are handled,
and the client does not parse 204 as JSON or loop indefinitely on 401. Mock transport
can unblock Anuska before the backend works; clearly distinguish mock and live mode.

## NAS-02 — onboarding/profile screen

Planned owned files: frontend/src/features/profile/* and frontend/src/features/auth/*.

- After login, GET /api/me; show onboarding only for PROFILE_NOT_FOUND.
- Prefill an available display name for confirmation; validate/edit via POST/PATCH.
- Returning users must retain their stored edits. Preserve input on save failures.
- Integrate Anuska's skill editor using the agreed component/client interface. Nasya
  makes the shell/import changes; do not both edit App.tsx or global CSS at once.
- Test loading, missing profile, validation errors, session expiry, failed save and reload.

Done when: new/returning users follow the contract and the combined screen works with
live Python endpoints after Jason's handoff. A mock-only demo is not completed integration.

## Boundaries and progress

Do not build direct Supabase queries for application tables. Do not implement a custom
login backend or rewrite Anuska's skill component. Future Discover work needs a contract.

Initial status: NAS-01/02 not verified complete; only the starter App and health call exist.
Inspect current state before starting. Append task/result/check/PR/next-step notes here.

### WP-7 progress note (overnight 2026-10-26)

- Branch: `feat/wp7-discover-ui`
- commit: `daa3a36` (Codex build) + `1973e16` (review fix round); orchestrator re-ran checks on `1973e16`: npm test 66 passed, npm run build clean
- Result: Discover feed UI, local mock and shared-transport real client adapter implemented; fresh independent review pending.
- Checks: `cd frontend && npm test` — 5 files, 58 tests passed.
- Checks: `cd frontend && npm run build` — TypeScript and Vite production build passed (95 modules).
- Checks: the real-client export switch was selected temporarily and `npm run build` passed; mock export restored afterward.
- Unverified: live backend/API, Supabase, MongoDB, browser visual review, and integrated profile-not-found redirect.
- Human steps: Zhihao independent review; switch to real client when the live Discover endpoint is integrated.
- Open questions: none for WP-7 contract; reviewer findings pending.
- Real-client switch: replace `export { mockDiscoverClient as discoverClient } from './mocks'` with `export { realDiscoverClient as discoverClient } from './realClient'`.

### WP-7 fix round (2026-10-26)

- Reviewer findings fixed: (1) filters/Check again/Try again are blocked while decision PUTs are pending, so a failed PUT always restores its card with a visible retry; (2) onProfileMissing guarded in its own try/catch after error/rollback state is set; (3) empty state hidden and "Saving your decision…" shown while PUTs are pending; (4) maxLength 100 on Location/Keyword plus a distinct validation_failed message; (5) 404 `job` drops the card with "This job is no longer available."; (6) real client PUT test asserts the URL; (7) focus moves to the next card, buttons named with the job title, aria-keyshortcuts on the first card; (8) "Open posting" only for http(s) URLs. Added tests for Change filters / Check again.
- Checks: `cd frontend && npm test` — 5 files, 66 tests passed; `npm run build` — passed.

### Redesign B2 Discover progress note (2026-10-26)

- Branch: `feat/redesign-b2-discover` (built by the JARVIS designer agent; Zhihao reviews and commits).
- Result: Discover restyled to "The Notebook" on the B1 foundation. One job card at a time, segmented
  coverage meter (one cell per required skill), arrow-key hints on Not interested / Save, plain check and
  dash markers for "You have" / "Missing" (not checkbox-shaped), inline failure with Retry, empty and
  loading states, and on mobile the filters open in a bottom sheet (Escape or the X closes it).
- Behaviour kept: optimistic remove, rollback + Retry, filter lock while a decision is pending, prefetch,
  Left/Right shortcuts (ignored while typing and while the sheet is open), 404 job drops the card,
  http(s)-only posting link. A missing profile now shows "Let's set up your profile first" with Go now.
- Preview scenes: `frontend/src/preview/scenes-b2.tsx` (`/__preview/discover-*` on the dev server).
- Tests: copy-driven assertions in `DiscoverFeed.test.tsx` updated to the new strings and the one-card view.
