/**
 * Real `SkillsClient` (ANU-02) — talks to Jason's actual endpoints via the
 * shared `skillsApi` (lib/api.ts), which itself is a thin wrapper over the
 * shared authenticated `request()`. No second Supabase session manager, no
 * separate fetch wrapper: this file only translates `ApiError` into the
 * smaller `SkillsClientError` shape `SkillEditor` expects.
 *
 * Routes confirmed directly against backend/app/routers/skills.py, now
 * merged into `anushka` via `dev` (PR #2):
 *   GET    /api/skills?q=&limit=        -> SkillSearchResponse
 *   PUT    /api/me/skills/{skill_id}    -> 204, no body
 *   DELETE /api/me/skills/{skill_id}    -> 204, no body, always succeeds
 */

import { ApiError } from '../../lib/api-client'
import { skillsApi } from '../../lib/api'
import type { SkillsClient, SkillsClientError } from './client'

function toSkillsClientError(cause: unknown): SkillsClientError {
  if (cause instanceof ApiError) {
    return { status: cause.status, code: cause.code, message: cause.message, details: cause.details }
  }
  // skillsApi (via request()) only ever throws ApiError, but this keeps the
  // adapter honest about its own contract rather than assuming that never changes.
  return { status: 0, code: 'network_error', message: 'Something did not work. Try again.' }
}

export function createRealSkillsClient(): SkillsClient {
  return {
    async search(query, limit) {
      try {
        return await skillsApi.search(query, limit)
      } catch (cause) {
        throw toSkillsClientError(cause)
      }
    },

    async add(skillId) {
      try {
        await skillsApi.add(skillId)
      } catch (cause) {
        throw toSkillsClientError(cause)
      }
    },

    async remove(skillId) {
      try {
        await skillsApi.remove(skillId)
      } catch (cause) {
        throw toSkillsClientError(cause)
      }
    },
  }
}

/**
 * Swap-in point for the shell (see docs/team/anushka-skill-editor-usage.md):
 * pass this as `SkillEditor`'s `client` prop instead of the default mock.
 * Nothing in `SkillEditor.tsx` itself changes for this swap.
 */
export const realSkillsClient: SkillsClient = createRealSkillsClient()
