/**
 * Contract for the confirmed-skill editor (ANU-01/02).
 *
 * This file intentionally does NOT redeclare `Skill` / `UserSkill` — those
 * already live in `../../types/api.ts` and stay the single source of truth.
 * Everything here is either (a) local to this feature, or (b) a proposed
 * shared-shape that needs a small, agreed edit to the shared files before
 * `SkillEditor` can be wired for real. See "PROPOSED SHARED CHANGES" below —
 * do not implement those elsewhere without Nasya's sign-off; this is the
 * hand-off artifact for that conversation, not a silent workaround.
 */

import type { SkillSearchResponse, UserSkill } from '../../types/api'

/**
 * `SkillSearchResponse` now lives in `types/api.ts` (added alongside `Skill`)
 * — it started as a proposal here and has since landed as a real shared
 * type, confirmed against Jason's actual `GET /api/skills` response shape.
 * Re-exported so existing imports of `SkillSearchResponse` from this file
 * (mocks.ts, client.ts) keep working without a competing declaration.
 */
export type { SkillSearchResponse }

/**
 * `MeResponse.skills: Skill[]` has landed in `types/api.ts` — this used to be
 * a proposed type here (`MeResponseWithSkills`) before it was confirmed and
 * merged; removed now that the real thing exists. `SkillEditor`'s
 * `confirmedSkills` prop should be sourced from `MeResponse.skills` directly.
 */

/**
 * `ProfileProvider.reload()` is now `() => Promise<void>` (auth/ProfileProvider.tsx)
 * — this used to document a proposed signature change; it's landed. Resolves
 * after the fetch settles, rejects on genuine failure, but not on "no
 * profile row yet" (a normal state, not an error). `SkillEditor` depends on
 * this to know when to clear a row's pending state against fresh data,
 * rather than guessing with a timeout.
 */
export type AsyncProfileReload = () => Promise<void>

/**
 * `ApiErrorCode` (types/api.ts) is a lowercase union (`not_found`,
 * `validation_failed`, `service_unavailable`, ...) matching the real backend
 * exactly (backend/app/errors.py + routers/skills.py, merged into `dev` and
 * now into `anushka`) — including reusing a single `not_found` for both a
 * missing profile and a missing skill, disambiguated by `details.resource`
 * rather than by separate codes. See client.ts's `isMissingResource()` for
 * the resource-disambiguation helper this implies. (An earlier draft of this
 * feature wrongly assumed docs/API.md's uppercase codes were current and
 * flagged the lowercase union as stale — that was backwards; docs/API.md was
 * the stale one.)
 */

/* -------------------------------------------------------------------------- */
/* SkillEditor props — the agreed integration surface with Nasya's shell       */
/* -------------------------------------------------------------------------- */

export interface SkillEditorProps {
  /** The student's currently confirmed skills, as returned by GET /api/me. */
  confirmedSkills: UserSkill[]
  /**
   * Re-fetches the profile (and its skills) from the shell's session of
   * truth after a successful add/remove. Must resolve only once fresh data
   * has landed — see `AsyncProfileReload` above. `SkillEditor` never mutates
   * `confirmedSkills` itself; the shell is the single owner of that state.
   */
  onProfileReload: AsyncProfileReload
  /** Optional root class for shell layout hooks; no global selectors. */
  className?: string
}

/* -------------------------------------------------------------------------- */
/* Local UI state — internal to this feature, not shared                      */
/* -------------------------------------------------------------------------- */

export type SkillRowStatus = 'idle' | 'pending' | 'error'

/** Per-skill-id UI state, so operations on different skills never block. */
export interface SkillRowState {
  status: SkillRowStatus
  /** Set only when status === 'error'; cleared on the next attempt. */
  errorMessage?: string
}

export type SkillOperation = 'add' | 'remove'