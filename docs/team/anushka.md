# Anushka — confirmed-skill editing

> **Current work (PRD v2, 25 Oct 2026):** WP-6 frontend (resume upload + suggested skills, mount SkillEditor), WP-8 (Vault screen), WP-9 (Skill Gap screen). Specs, allowed files and
> acceptance criteria are in [PRD.md §5](../PRD.md); shapes in [API.md](../API.md).
> Task IDs below are from the first milestone; check their progress notes before reusing them.

Read [team workflow](README.md), [setup](../README.md), [PRD](../PRD.md) and
[API contract](../API.md). Own the skill editor in the first milestone; Nasya owns
the profile shell, authentication and shared API client.

## ANU-01 — skill editor against contract-shaped mocks

Planned owned files: frontend/src/features/skills/* (component, local styles and tests).

- Agree SkillEditor props and shared client exports with Nasya before implementation.
  Start from confirmed skills plus an async profile-reload callback. Agree exact types
  in a small shared change; do not create a competing global client/types module.
- Search GET /api/skills, display results/empty state and ask for a narrower query when
  has_more is true. Handle stale search responses so old results do not replace newer ones.
- Add with PUT /api/me/skills/{skill_id}; remove with DELETE. No free-text dictionary
  creation. Handle 204 without parsing a body; refresh GET /api/me on success.
- Serialize operations on the same skill and show pending/error state. Do not claim
  failed operations were saved or replay old skill edits automatically offline.
- Provide synthetic mocks with the exact API shapes, including empty results,
  SKILL_NOT_FOUND, validation and service failures. Mock IDs need not equal live seed IDs.

Done when: search/select/remove behaviours and failures are tested in isolation, the
component accepts its agreed inputs, and styling stays local to avoid shell conflicts.

## ANU-02 — integrate with Nasya and Jason

- Deliver the component/export and usage notes to Nasya, who wires the application shell.
- Use the common authenticated client; do not create a second Supabase session manager.
- Test adding/removing and reloading against Jason's live endpoints with real test-user
  identity and canonical skill IDs from the actual lookup response.

Done when: confirmed skills survive reload, no-op operations work, logout/account changes
do not show a previous user's skills, and integration is recorded beyond mock-only checks.

## Boundaries and progress

Coordinate package/test-tool additions through Nasya. Do not edit App.tsx, global CSS or
shared dependency files concurrently. Vault/Tracker and Skill Gap screens are later tasks
and require their API contracts before implementation.

Initial status: ANU-01/02 not verified complete; skill UI/client integration is not built.
Inspect current state before starting. Append task/result/check/PR/next-step notes here.

### 2026-09-25 — ANU-01 verified complete; three shared diffs drafted; ANU-02 blocked

**Result:** Re-verified from a fresh clone of `anushka` (not a cached copy):
`npm install && npm run test` → 35/35 passing; `npm run build` (strict
`tsc --noEmit` + Vite production build) → clean. Error handling now matches
the real backend contract (lowercase `not_found`/`validation_failed`/
`service_unavailable`, skill vs. profile disambiguated by `details.resource`,
not by separate codes — confirmed against Jason's actual implementation on
`jason/seedskills`/`dev`, not just `docs/API.md`, which is stale on this
point).

**Shared-file diffs — drafted and verified together (35/35, clean build with
all three applied), not yet reviewed by Nasya or merged:**
1. `frontend/src/types/api.ts` — `MeResponse.skills: Skill[]` added, matching
   Jason's real schema exactly.
2. `frontend/src/types/api.ts` — `ApiErrorCode` gains `'service_unavailable'`,
   which the real backend emits but the union was missing.
3. `frontend/src/auth/ProfileProvider.tsx` — `reload` promisified from
   `() => void` to `() => Promise<void>`, resolving after the fetch settles
   and rejecting on genuine failure (not on the "no profile row yet" case,
   which stays a normal state). Checked: no other call site in the app reads
   `reload`, so this is a safe signature change on its own.

**New file:** `docs/team/anushka-skill-editor-usage.md` — hand-off notes for
Nasya: exact `<SkillEditor>` props, the two dependencies above, and what
still needs building before this is live (see next steps).

**Still open, in priority order:**
1. Get the three diffs above reviewed/merged — they're Nasya's shared files
   per this doc's own boundaries.
2. Build a real `SkillsClient` adapter (see `features/skills/client.ts`'s
   interface) against `lib/api.ts`, once #1 lands.
3. Nasya mounts `<SkillEditor>` in `ProfileScreen.tsx` (currently still shows
   placeholder copy — checked directly, no `SkillEditor` reference anywhere
   in `App.tsx` or `ProfileScreen.tsx` yet).
4. Merge/rebase `dev` into `anushka` — `backend/app/routers/skills.py` exists
   on `dev` (from `jason/seedskills`) but not on this branch yet, so live
   endpoint testing per ANU-02 isn't possible here until that happens.
5. Open an actual PR for this work. Checked the repo's open PRs directly:
   the only one (#1) is Jason's `seedskills` PR into `dev` — nothing has been
   opened for the skill editor yet.

### 2026-09-26 — correcting the record: items 1 and 4 above are done

The two entries above are now stale and could mislead anyone reading this
log top-to-bottom without checking the branch directly, so: verified fresh
(`git log`, `git clone --depth 1 -b anushka`, direct file inspection — not
assumed from memory of an earlier session):

- **Item 4 (merge `dev` into `anushka`) is done.** `f296eed "Merge pull
  request #2 from anushka2503769/dev"` is on this branch.
  `backend/app/routers/skills.py`, `sql_skills.py`, and the `not_found`/
  `service_unavailable` error handling in `errors.py` are all present and
  wired into `main.py` (`app.include_router(skills.router)`). This is real,
  functioning backend code, not a stub — checked the actual file contents,
  not just that the merge commit exists.
- **Item 1 (the three shared-type/provider diffs) landed as part of that
  same merge** and are confirmed present: `MeResponse.skills: Skill[]`,
  `ApiErrorCode` includes `'service_unavailable'`, and
  `ProfileProvider.reload` is `() => Promise<void>`.

**Still genuinely open** (re-verified, not carried over from memory):
- `.github/workflows/ci.yml` still has no `npm run test` step for the
  frontend job — checked directly, the line isn't there. My earlier drafted
  diff for this was handed over as a file but was never actually merged.
- `<SkillEditor>` is still not mounted anywhere — still zero matches for
  `SkillEditor` in `App.tsx` or `ProfileScreen.tsx`. Still Nasya's file
  (profile shell), not touched here.
- No PR into `dev` exists yet for the skill-editor frontend work itself
  (`realClient.ts` + the `skillsApi` addition below) — opening one is next.

### WP-8 progress note (overnight 2026-10-26)

- Branch: `feat/wp8-vault-ui`.
- commit: `ac1a9a8` (Codex build) + `97d8d52` (review fix round); orchestrator re-ran checks on `97d8d52`: npm test 70 passed, npm run build clean
- Result: Vault tracker screen, contract-shaped stateful mock, and real shared-transport adapter implemented. Current default remains MOCK.
- Checks: `cd frontend && npm test` — 6 files, 58 tests passed. `cd frontend && npm run build` — TypeScript and Vite production build passed (94 modules transformed).
- Unverified: no live WP-2/backend integration or manual browser walkthrough; no shared database or network calls were made.
- Questions: none. Integration can switch to the real adapter when WP-2 is available on dev.
- Exact real-client switch in `frontend/src/features/tracker/defaultClient.ts`: replace `import { createMockTrackerClient as createTrackerClient } from './mocks'` with `import { createRealTrackerClient as createTrackerClient } from './realClient'`.


### WP-8 fix round (2026-10-26)

- Branch: `feat/wp8-vault-ui`.
- commit: `ac1a9a8` (Codex build) + `97d8d52` (review fix round); orchestrator re-ran checks on `97d8d52`: npm test 70 passed, npm run build clean
- Findings 1–3 fixed: status changes on the last page step back and reload; page controls lock during writes; empty states use the filtered visible rows.
- Finding 4 fixed: accessible inline confirmation supports Cancel, Remove, Escape, initial focus and focus return; DELETE failure leaves the row and confirmation open.
- Findings 5–6 fixed: posting links require HTTP(S); inactive listings show “No longer listed” while status remains editable.
- Finding 7 fixed: UI uses `toDisplayMessage`; real adapter preserves `ApiError` status/code/details and 5xx messages are masked.
- Finding 8 fixed: mock PUT creates known active untracked rows, same-status PUT preserves `updated_at`, changed status advances it, unknown/inactive jobs return 404, and 23 synthetic SAVED rows are seeded.
- Finding 9 fixed: all six count tabs link to the tab panel and Arrow keys move selection/focus.
- Missing coverage added: failed status updates restore both row/status and counts; six tab labels/counts are asserted.
- Checks: `cd frontend && npm test` — 6 files, 70 tests passed. `cd frontend && npm run build` — TypeScript passed; Vite transformed 94 modules and built in 111ms. `git diff --check` passed.
- Unverified: no live WP-2 backend integration or manual browser walkthrough; no network/shared database calls were made.
- Questions: none.

### WP-8 fix round final verification update (2026-10-26)

- Branch: `feat/wp8-vault-ui`.
- commit: `2fa8006` (helper edits after `f7ce324`, reviewed and committed by the orchestrator). Orchestrator re-run on `2fa8006`: `npm test` 6 files / 72 tests passed, `npm run build` ✓, `git diff --check` clean.
- Final check results after adding successful DELETE, pending DELETE navigation, two-way tab-keyboard, and pending/rollback count assertions: `cd frontend && npm test` — 6 files, 72 tests passed; `cd frontend && npm run build` — TypeScript passed, Vite transformed 94 modules and built in 129ms; `git diff --check` passed.
- Confirmation action label is `Remove`, scoped within the accessible confirmation group.
- Remaining unverified: live WP-2 integration and manual browser walkthrough. Questions: none.
