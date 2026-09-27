import { request } from './api-client'
import type {
  CreateProfileRequest,
  MeResponse,
  Profile,
  SkillSearchResponse,
  UpdateProfileRequest,
} from '../types/api'

/** Typed helpers for the profile endpoints used by the auth shell. */
export const profileApi = {
  get(signal?: AbortSignal): Promise<MeResponse> {
    return request<MeResponse>('/me', { signal })
  },

  create(payload: CreateProfileRequest): Promise<MeResponse> {
    return request<MeResponse>('/me', { method: 'POST', body: payload })
  },

  update(payload: UpdateProfileRequest): Promise<Profile> {
    return request<Profile>('/me', { method: 'PATCH', body: payload })
  },
}

/**
 * Typed helpers for the skill dictionary and confirmed-skill membership
 * endpoints (backend/app/routers/skills.py). Thin and additive, same shape
 * as `profileApi` above: each method is a one-line call to the shared
 * `request()` client, no new fetch wrapper and no second session manager.
 */
export const skillsApi = {
  search(query: string, limit?: number, signal?: AbortSignal): Promise<SkillSearchResponse> {
    return request<SkillSearchResponse>('/skills', { query: { q: query, limit }, signal })
  },

  /** PUT /api/me/skills/{id} — 204, no body, including the "already confirmed" no-op case. */
  add(skillId: number, signal?: AbortSignal): Promise<void> {
    return request<void>(`/me/skills/${skillId}`, { method: 'PUT', signal })
  },

  /** DELETE /api/me/skills/{id} — 204, no body, always succeeds (idempotent). */
  remove(skillId: number, signal?: AbortSignal): Promise<void> {
    return request<void>(`/me/skills/${skillId}`, { method: 'DELETE', signal })
  },
}
