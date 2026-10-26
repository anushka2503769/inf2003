import { ApiError, request } from '../../lib/api-client'
import { skillsApi } from '../../lib/api'
import type { SkillGapClient, SkillGapClientError, SkillGapRolesResponse, SkillGapResponse } from './types'

function toClientError(cause: unknown): SkillGapClientError {
  if (cause instanceof ApiError) return { status: cause.status, code: cause.code, message: cause.message, details: cause.details }
  return { status: 0, code: 'network_error', message: 'Cannot reach the server. Check that the API is running, then try again.' }
}
export function createRealSkillGapClient(): SkillGapClient {
  return {
    async roles(signal) {
      try { return await request<SkillGapRolesResponse>('/skill-gap/roles', { signal }) }
      catch (cause) { throw toClientError(cause) }
    },
    async forRole(role, signal) {
      try { return await request<SkillGapResponse>('/me/skill-gap', { query: { role_category: role, limit: 30 }, signal }) }
      catch (cause) { throw toClientError(cause) }
    },
    async add(skillId) {
      try { await skillsApi.add(skillId) }
      catch (cause) { throw toClientError(cause) }
    },
  }
}
export const realSkillGapClient = createRealSkillGapClient()
