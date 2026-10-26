/** Wire shapes for the resume routes (docs/API.md section 5). */

import type { Skill } from '../../types/api'

export interface ResumeExtractedData {
  skills: string[]
  education: object[]
  experience: object[]
  projects: object[]
}

export interface ResumeResponse {
  resume_id: string
  user_id: string
  file_name: string
  uploaded_at: string
  extracted_data: ResumeExtractedData
  /** Dictionary skills found in the resume that the student has not confirmed yet. */
  suggested_skills: Skill[]
}

/** Just what the UI needs from a failed call; same idea as `SkillsClientError`. */
export interface ResumeClientError {
  status: number
  code: string
  message: string
  details?: Record<string, unknown>
}

export function isResumeClientError(value: unknown): value is ResumeClientError {
  return (
    typeof value === 'object' &&
    value !== null &&
    'status' in value &&
    'code' in value &&
    'message' in value
  )
}
