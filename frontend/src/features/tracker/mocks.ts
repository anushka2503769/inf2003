import { ApiError } from '../../lib/api-client'
import type { TrackerClient } from './client'
import type { JobSummary, TrackerItem, TrackerStatus, TrackerSummary } from './types'

const STATUSES: readonly TrackerStatus[] = ['NOT_INTERESTED', 'SAVED', 'APPLIED', 'INTERVIEW', 'REJECTED', 'OFFER']
const MOCK_UPDATED_AT = '2026-10-26T01:00:00Z'

const MOCK_ITEMS: TrackerItem[] = Array.from({ length: 23 }, (_, index) => {
  const suffix = String(index + 1).padStart(12, '0')
  return {
    job: {
      job_id: `10000000-0000-4000-8000-${suffix}`,
      title: index === 0 ? 'Graduate Software Engineer' : `Synthetic Tracker Role ${index + 1}`,
      company_name: index === 0 ? 'Example Labs' : `Example Company ${index + 1}`,
      location: 'Singapore',
      job_type: index % 2 === 0 ? 'FULL_TIME' : 'INTERNSHIP',
      work_arrangement: index % 2 === 0 ? 'HYBRID' : 'REMOTE',
      application_url: `https://example.test/jobs/${index + 1}`,
      source: 'synthetic',
      source_posted_at: '2026-10-20T00:00:00Z',
      is_active: true,
    },
    status: 'SAVED',
    created_at: '2026-10-20T10:00:00Z',
    updated_at: `2026-10-26T00:${String(59 - index).padStart(2, '0')}:00Z`,
  }
})

const EXTRA_JOBS: readonly JobSummary[] = [
  {
    job_id: '90000000-0000-4000-8000-000000000001',
    title: 'Product Analyst Intern',
    company_name: 'Synthetic Ventures',
    location: 'Singapore',
    job_type: 'INTERNSHIP',
    work_arrangement: 'ONSITE',
    application_url: 'https://example.test/jobs/untracked-active',
    source: 'synthetic',
    source_posted_at: null,
    is_active: true,
  },
  {
    job_id: '90000000-0000-4000-8000-000000000002',
    title: 'Closed Synthetic Role',
    company_name: 'Synthetic Ventures',
    location: null,
    job_type: null,
    work_arrangement: null,
    application_url: 'https://example.test/jobs/inactive',
    source: 'synthetic',
    source_posted_at: null,
    is_active: false,
  },
]

function counts(items: readonly TrackerItem[]): TrackerSummary {
  const result = Object.fromEntries(STATUSES.map(status => [status, 0])) as Record<TrackerStatus, number>
  items.forEach(item => { result[item.status] += 1 })
  return { counts: result, total: items.length }
}

/** Stateful, contract-shaped synthetic tracker data. Each client owns its copy. */
export function createMockTrackerClient(seed: readonly TrackerItem[] = MOCK_ITEMS): TrackerClient {
  const items = seed.map(item => ({ ...item, job: { ...item.job } }))
  let nextTimestamp = Date.parse(MOCK_UPDATED_AT) + 1000
  const knownJobs = new Map<string, JobSummary>([
    ...items.map(item => [item.job.job_id, { ...item.job }] as const),
    ...EXTRA_JOBS.map(job => [job.job_id, { ...job }] as const),
  ])
  return {
    async summary() {
      return counts(items)
    },
    async list(status, limit, offset) {
      const matching = items
        .filter(item => status === undefined || (Array.isArray(status) ? status.includes(item.status) : item.status === status))
        .sort((a, b) => b.updated_at.localeCompare(a.updated_at) || a.job.job_id.localeCompare(b.job.job_id))
      return { items: matching.slice(offset, offset + limit).map(item => ({ ...item, job: { ...item.job } })), total: matching.length }
    },
    async update(jobId, status) {
      const current = items.find(item => item.job.job_id === jobId)
      if (current) {
        if (current.status !== status) {
          current.status = status
          current.updated_at = new Date(nextTimestamp).toISOString()
          nextTimestamp += 1000
        }
        return { ...current, job: { ...current.job } }
      }
      const job = knownJobs.get(jobId)
      if (!job || !job.is_active) {
        throw new ApiError(404, 'not_found', 'Job not found.', { resource: 'job' })
      }
      const created: TrackerItem = {
        job: { ...job },
        status,
        created_at: MOCK_UPDATED_AT,
        updated_at: MOCK_UPDATED_AT,
      }
      items.push(created)
      return { ...created, job: { ...created.job } }
    },
    async remove(jobId) {
      const index = items.findIndex(item => item.job.job_id === jobId)
      if (index >= 0) items.splice(index, 1)
    },
  }
}
