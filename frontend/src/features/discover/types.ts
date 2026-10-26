import type { JobType, RequirementType, WorkArrangement, UserJobStatus, Uuid } from '../../types/api'

export interface JobSummary {
  job_id: Uuid
  source: string
  title: string
  company_name: string
  location: string | null
  job_type: JobType | null
  work_arrangement: WorkArrangement | null
  application_url: string
  source_posted_at: string | null
  is_active: boolean
}

export interface DiscoverFilters {
  job_type?: JobType
  work_arrangement?: WorkArrangement
  location?: string
  q?: string
}

export interface SkillRequirement {
  skill_id: number
  name: string
  requirement_type: RequirementType
}

export interface DiscoverMatch {
  required_total: number
  required_matched: number
  preferred_total: number
  preferred_matched: number
  coverage: number | null
  matched_skills: SkillRequirement[]
  missing_skills: SkillRequirement[]
}

export interface DiscoverItem {
  job: JobSummary
  match: DiscoverMatch
  rank: number
}

export interface DiscoverResponse {
  items: DiscoverItem[]
  has_more: boolean
}

export type DiscoverDecision = Extract<UserJobStatus, 'NOT_INTERESTED' | 'SAVED'>
