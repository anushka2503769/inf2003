import type { TrackerClient } from './client'
import type { TrackerItem, TrackerStatus, TrackerSummary } from './types'

const STATUSES: readonly TrackerStatus[] = ['NOT_INTERESTED', 'SAVED', 'APPLIED', 'INTERVIEW', 'REJECTED', 'OFFER']

const MOCK_ITEMS: TrackerItem[] = [
  {
    job: {
      job_id: '10000000-0000-4000-8000-000000000001',
      title: 'Graduate Software Engineer',
      company_name: 'Example Labs',
      location: 'Singapore',
      job_type: 'FULL_TIME',
      work_arrangement: 'HYBRID',
      application_url: 'https://example.test/jobs/graduate-engineer',
      source: 'synthetic',
      source_posted_at: '2026-10-20T00:00:00Z',
      is_active: true,
    },
    status: 'SAVED',
    created_at: '2026-10-20T10:00:00Z',
    updated_at: '2026-10-25T10:00:00Z',
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
      if (!current) throw { status: 404, code: 'not_found', message: 'Job not found.', details: { resource: 'job' } }
      current.status = status
      current.updated_at = new Date().toISOString()
      return { ...current, job: { ...current.job } }
    },
    async remove(jobId) {
      const index = items.findIndex(item => item.job.job_id === jobId)
      if (index >= 0) items.splice(index, 1)
    },
  }
}
