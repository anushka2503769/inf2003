export interface SkillGapRole {
  role_category: string
  job_count: number
}

export interface SkillGapRolesResponse {
  items: SkillGapRole[]
}

export interface SkillGapRow {
  skill_id: number
  name: string
  job_count: number
  frequency: number
  required_count: number
  preferred_count: number
  max_minimum_years: number | null
  years_mentions: number
  user_has: boolean
}

export interface SkillGapResponse {
  role_category: string
  sample_size: number
  skills: SkillGapRow[]
  summary: { top_n: number; user_has_in_top_n: number }
}

export interface SkillGapClientError {
  status: number
  code: string
  message: string
  details?: Record<string, unknown>
}

export interface SkillGapClient {
  roles(signal?: AbortSignal): Promise<SkillGapRolesResponse>
  forRole(role: string, signal?: AbortSignal): Promise<SkillGapResponse>
  add(skillId: number): Promise<void>
}
