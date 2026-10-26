import { env } from '../../lib/env'
import { profileApi } from '../../lib/api'
import type { MeResponse } from '../../types/api'
import { realSkillsClient } from '../skills/realClient'
import type { SkillsClient } from '../skills/client'
import { mockLoadProfile, mockResumeClient, mockSkillsClientForProfile } from './mocks'
import { realResumeClient } from './realClient'
import type { ResumeResponse } from './types'

export interface ResumeClient {
  /** The caller's current resume, or null when none has been uploaded (404 resource "resume"). */
  current(): Promise<ResumeResponse | null>
  /** POST /api/resumes/upload. Rejects with a `ResumeClientError`. */
  upload(file: File): Promise<ResumeResponse>
}

/*
 * The one place the Profile screen's data source is chosen. The real API by
 * default; VITE_DATA=mock switches all three to synthetic data.
 */
export const resumeClient: ResumeClient = env.useMockData ? mockResumeClient : realResumeClient
export const profileSkillsClient: SkillsClient = env.useMockData ? mockSkillsClientForProfile : realSkillsClient
export const loadProfile: () => Promise<MeResponse> = env.useMockData ? mockLoadProfile : () => profileApi.get()
