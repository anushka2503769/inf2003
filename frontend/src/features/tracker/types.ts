export const TRACKER_STATUSES = [
  'NOT_INTERESTED',
  'SAVED',
  'APPLIED',
  'INTERVIEW',
  'REJECTED',
  'OFFER',
] as const

export type TrackerStatus = (typeof TRACKER_STATUSES)[number]
export type JobType = 'FULL_TIME' | 'PART_TIME' | 'INTERNSHIP' | null
export type WorkArrangement = 'ONSITE' | 'HYBRID' | 'REMOTE' | null

export interface JobSummary {
  job_id: string
  title: string
  company_name: string
  location: string | null
  job_type: JobType
  work_arrangement: WorkArrangement
  application_url: string
  source: string
  source_posted_at: string | null
  is_active: boolean
}

export interface TrackerItem {
  job: JobSummary
  status: TrackerStatus
  created_at: string
  updated_at: string
}

export interface TrackerSummary {
  counts: Record<TrackerStatus, number>
  total: number
}

export interface TrackerPage {
  items: TrackerItem[]
  total: number
}
