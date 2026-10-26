import type { DiscoverClient } from './client'
import type { DiscoverFilters, DiscoverItem, DiscoverResponse } from './types'

const REQUIRED = { skill_id: 9101, name: 'Python', requirement_type: 'REQUIRED' as const }
const MISSING = { skill_id: 9102, name: 'SQL', requirement_type: 'REQUIRED' as const }

/** Synthetic contract-shaped postings; IDs are intentionally fixture-only UUIDs. */
export const MOCK_DISCOVER_ITEMS: DiscoverItem[] = [
  {
    job: { job_id: '00000000-0000-4000-8000-000000000101', source: 'fixture', title: 'Graduate Software Engineer', company_name: 'Northstar Labs', location: 'Singapore', job_type: 'INTERNSHIP', work_arrangement: 'HYBRID', application_url: 'https://example.test/jobs/101', source_posted_at: '2026-10-20T00:00:00Z', is_active: true },
    match: { required_total: 2, required_matched: 2, preferred_total: 1, preferred_matched: 1, coverage: 1, matched_skills: [REQUIRED, { skill_id: 9103, name: 'TypeScript', requirement_type: 'REQUIRED' }, { skill_id: 9104, name: 'Communication', requirement_type: 'PREFERRED' }], missing_skills: [] }, rank: 1,
  },
  {
    job: { job_id: '00000000-0000-4000-8000-000000000102', source: 'fixture', title: 'Junior QA Engineer', company_name: 'Cedar Systems', location: 'Remote', job_type: 'FULL_TIME', work_arrangement: 'REMOTE', application_url: 'https://example.test/jobs/103', source_posted_at: '2026-10-16T00:00:00Z', is_active: true },
    match: { required_total: 1, required_matched: 1, preferred_total: 1, preferred_matched: 1, coverage: 1, matched_skills: [REQUIRED, { skill_id: 9104, name: 'Communication', requirement_type: 'PREFERRED' }], missing_skills: [] }, rank: 2,
  },
  {
    job: { job_id: '00000000-0000-4000-8000-000000000103', source: 'fixture', title: 'Product Data Intern', company_name: 'Paper Co', location: 'Singapore', job_type: 'INTERNSHIP', work_arrangement: 'ONSITE', application_url: 'https://example.test/jobs/102', source_posted_at: '2026-10-18T00:00:00Z', is_active: true },
    match: { required_total: 2, required_matched: 1, preferred_total: 0, preferred_matched: 0, coverage: 0.5, matched_skills: [REQUIRED], missing_skills: [MISSING] }, rank: 3,
  },
  {
    job: { job_id: '00000000-0000-4000-8000-000000000104', source: 'fixture', title: 'Frontend Developer', company_name: 'Blue Folder', location: 'Singapore', job_type: 'PART_TIME', work_arrangement: 'HYBRID', application_url: 'https://example.test/jobs/104', source_posted_at: null, is_active: true },
    match: { required_total: 0, required_matched: 0, preferred_total: 0, preferred_matched: 0, coverage: null, matched_skills: [], missing_skills: [] }, rank: 4,
  },
]

const PAGE_SIZE = 20
const decisions = new Map<string, string>()
const latency = () => new Promise(resolve => setTimeout(resolve, 90))

function matches(item: DiscoverItem, filters: DiscoverFilters): boolean {
  const { job } = item
  return (filters.job_type === undefined || job.job_type === filters.job_type) &&
    (filters.work_arrangement === undefined || job.work_arrangement === filters.work_arrangement) &&
    (filters.location === undefined || (job.location ?? '').toLowerCase().includes(filters.location.toLowerCase())) &&
    (filters.q === undefined || `${job.title} ${job.company_name}`.toLowerCase().includes(filters.q.toLowerCase()))
}

export const mockDiscoverClient: DiscoverClient = {
  async list(filters, offset, limit = PAGE_SIZE): Promise<DiscoverResponse> {
    await latency()
    const items = MOCK_DISCOVER_ITEMS.filter(item => !decisions.has(item.job.job_id) && matches(item, filters))
    return { items: items.slice(offset, offset + limit), has_more: items.length > offset + limit }
  },
  async decide(jobId, status) {
    await latency()
    decisions.set(jobId, status)
  },
}
