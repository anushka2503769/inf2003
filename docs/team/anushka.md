# Anushka — confirmed-skill editing

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