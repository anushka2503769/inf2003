/**
 * Shared API types for the Jobless Simulator frontend.
 *
 * This file is the single frontend source of truth for request/response shapes.
 * Screens must not redeclare these locally. Field names and enum values mirror
 * docs/erd.md; changing either requires updating docs/erd.md, docs/api-contract.md
 * and the FastAPI schemas together.
 *
 * Sections marked "contract only" describe endpoints that are agreed but not yet
 * implemented. Import them when building those screens so the shapes stay aligned.
 */

/* -------------------------------------------------------------------------- */
/* Enumerations (docs/erd.md)                                                  */
/* -------------------------------------------------------------------------- */

/** An internship is INTERNSHIP even when it is full time. */
export const JOB_TYPES = ['FULL_TIME', 'PART_TIME', 'INTERNSHIP'] as const
export type JobType = (typeof JOB_TYPES)[number]

export const WORK_ARRANGEMENTS = ['ONSITE', 'HYBRID', 'REMOTE'] as const
export type WorkArrangement = (typeof WORK_ARRANGEMENTS)[number]

export const USER_JOB_STATUSES = [
  'NOT_INTERESTED',
  'SAVED',
  'APPLIED',
  'INTERVIEW',
  'REJECTED',
  'OFFER',
] as const
export type UserJobStatus = (typeof USER_JOB_STATUSES)[number]

export const REQUIREMENT_TYPES = ['REQUIRED', 'PREFERRED'] as const
export type RequirementType = (typeof REQUIREMENT_TYPES)[number]

/* -------------------------------------------------------------------------- */
/* Primitives                                                                  */
/* -------------------------------------------------------------------------- */

/** UUID string as produced by PostgreSQL. */
export type Uuid = string

/** ISO 8601 timestamp with offset, e.g. 2026-09-12T04:21:00Z. */
export type IsoTimestamp = string

/* -------------------------------------------------------------------------- */
/* Errors                                                                      */
/* -------------------------------------------------------------------------- */

/**
 * Every non-2xx JSON response uses this envelope so the client can branch on a
 * stable machine-readable code rather than on prose.
 */
export interface ApiErrorBody {
  error: {
    code: ApiErrorCode
    message: string
    details?: Record<string, unknown>
  }
}

export type ApiErrorCode =
  | 'unauthenticated'
  | 'forbidden'
  | 'not_found'
  | 'validation_failed'
  | 'conflict'
  | 'rate_limited'
  | 'internal_error'
  /** Client-side only: request aborted or the network never answered. */
  | 'network_error'
  /** Client-side only: the response was not the JSON shape we agreed on. */
  | 'malformed_response'

/* -------------------------------------------------------------------------- */
/* Profile — implemented                                                       */
/* -------------------------------------------------------------------------- */

/**
 * A row in the SQL `users` table. `user_id` equals the Supabase auth subject,
 * so the browser never sends it; the backend reads it from the bearer token.
 *
 * Email and avatar deliberately live in the auth session rather than here,
 * because docs/erd.md does not store them.
 */
export interface Profile {
  user_id: Uuid
  full_name: string
  created_at: IsoTimestamp
  updated_at: IsoTimestamp
}

/** POST /api/me — first write after Google sign-in, creates the users row. */
export interface CreateProfileRequest {
  full_name: string
}

/** PATCH /api/me — name editing. Omitted keys are left unchanged. */
export interface UpdateProfileRequest {
  full_name?: string
}

/**
 * GET /api/me
 *
 * `onboarding_complete` is returned rather than inferred client-side, so that
 * later onboarding steps (resume upload, skill confirmation) can flip it
 * without the frontend having to re-derive the rule.
 */
export interface MeResponse {
  profile: Profile
  onboarding_complete: boolean
}

/* -------------------------------------------------------------------------- */
/* Skills — contract only, endpoints not implemented                           */
/* -------------------------------------------------------------------------- */

export interface Skill {
  skill_id: number
  name: string
}

/** A skill the student has confirmed, as stored in SQL `user_skills`. */
export interface UserSkill {
  skill_id: number
  name: string
}

/* -------------------------------------------------------------------------- */
/* Jobs — contract only, endpoints not implemented                             */
/* -------------------------------------------------------------------------- */

export interface JobSkill {
  skill_id: number
  name: string
  requirement_type: RequirementType
}

export interface Job {
  job_id: Uuid
  source: string
  external_job_id: string
  title: string
  company_name: string
  location: string | null
  job_type: JobType | null
  work_arrangement: WorkArrangement | null
  application_url: string
  source_posted_at: IsoTimestamp | null
  is_active: boolean
}

/**
 * Skill coverage for one job and one student. Describe this to students as
 * skill coverage, never as a hiring probability (docs/PRD.md).
 */
export interface JobMatch {
  job: Job
  matched_skills: JobSkill[]
  missing_skills: JobSkill[]
  /** Share of the job's REQUIRED skills the student has confirmed, 0–1. */
  coverage: number
}

/** A row in SQL `user_jobs`: the current decision for one student and job. */
export interface UserJobRecord {
  job_id: Uuid
  status: UserJobStatus
  created_at: IsoTimestamp
  updated_at: IsoTimestamp
}

/** Session filters for Discover. Not persisted as user preferences. */
export interface DiscoverFilters {
  location?: string
  job_type?: JobType
  work_arrangement?: WorkArrangement
}

/* -------------------------------------------------------------------------- */
/* Pagination — contract only                                                  */
/* -------------------------------------------------------------------------- */

export interface Page<T> {
  items: T[]
  /** Opaque cursor for the next page, or null when the feed is exhausted. */
  next_cursor: string | null
}
