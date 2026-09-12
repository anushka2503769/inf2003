import { request } from './api-client'
import type {
  CreateProfileRequest,
  MeResponse,
  Profile,
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
