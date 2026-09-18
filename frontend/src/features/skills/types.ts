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

import type { Skill, UserSkill } from '../../types/api'

/* -------------------------------------------------------------------------- */
/* PROPOSED SHARED CHANGES (types/api.ts, lib/api.ts) — not yet implemented    */
/* -------------------------------------------------------------------------- */

/**
 * docs/API.md `GET /api/skills` returns `{ items, has_more }`, not the
 * cursor-based `Page<T>` already declared in `types/api.ts`. Proposing this
 * as a new named shape (`SkillSearchResponse`) rather than changing `Page<T>`,
 * since `Page<T>` may already be agreed for a different, cursor-based route.
 *
 * Proposed home: types/api.ts, alongside `Skill`.
 */
export interface SkillSearchResponse {
  items: Skill[]
  has_more: boolean
}

/**
 * `MeResponse` (types/api.ts) currently has no `skills` field, even though
 * POST/GET/PATCH /api/me all return one per docs/API.md. `SkillEditor` needs
 * this list as its `confirmedSkills` prop. Proposing the shared type gain a
 * `skills: UserSkill[]` field rather than this feature re-fetching it
 * separately, so there is exactly one place profile+skills are read together.
 *
 * Proposed home: types/api.ts, as `MeResponse.skills` and `Profile`-adjacent
 * (exact placement — on `Profile` vs. sibling on `MeResponse` — is Nasya's
 * call, since `ProfileProvider` owns `Profile`).
 */
export type MeResponseWithSkills = {
  skills: UserSkill[]
}

/**
 * `ProfileProvider.reload()` today is `() => void` (bumps a token; the fetch
 * effect re-runs and there is no way for a caller to know when it settles).
 * My task doc calls for "an async profile-reload callback" — `SkillEditor`
 * needs to know when the post-write GET /api/me has actually landed, so it
 * can clear a row's pending state against fresh data rather than guessing
 * with a timeout. Proposing `reload(): Promise<void>` (resolves after the
 * fetch settles, rejects only if the fetch itself throws outside the
 * existing catch — i.e. practically never) replace the current signature.
 *
 * Proposed home: auth/ProfileProvider.tsx, `ProfileContextValue.reload`.
 */
export type AsyncProfileReload = () => Promise<void>

/**
 * `ApiErrorCode` (types/api.ts) is a lowercase union (`not_found`,
 * `validation_failed`, ...) but docs/API.md specifies uppercase codes
 * (`SKILL_NOT_FOUND`, `PROFILE_NOT_FOUND`, `VALIDATION_ERROR`,
 * `SERVICE_UNAVAILABLE`) and `api-client.ts` passes `body.code` through
 * unchecked. As written, `error.code === 'not_found'` can never match a real
 * `PROFILE_NOT_FOUND` response — this affects existing code (ProfileProvider)
 * as well as this feature. Not fixing it here since it's a shared-file change
 * with app-wide blast radius; flagging so `SkillEditor`'s own error handling
 * doesn't quietly encode the same mismatch. `SkillEditor` will compare against
 * the literal contract strings below until the shared union is corrected.
 */
export const SKILL_ERROR_CODES = {
  skillNotFound: 'SKILL_NOT_FOUND',
  profileNotFound: 'PROFILE_NOT_FOUND',
  validation: 'VALIDATION_ERROR',
  serviceUnavailable: 'SERVICE_UNAVAILABLE',
} as const

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