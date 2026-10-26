import { useEffect, type ReactNode } from 'react'
import { Route, Routes } from 'react-router-dom'

import { AppShell } from '../app/AppShell'
import { routes } from '../app/routes'
import type { DiscoverClient } from '../features/discover/client'
import { DiscoverFeed } from '../features/discover/DiscoverFeed'
import type { DiscoverItem, SkillRequirement } from '../features/discover/types'
import type { PreviewScene } from './types'

/** Preview scenes for Discover (redesign B2). Dev server only. */
const GROUP = 'B2 Discover'

/* ------------------------------------------------------------------ fake data (hand-off copy) */

const skill = (skill_id: number, name: string, required: boolean): SkillRequirement => ({
  skill_id,
  name,
  requirement_type: required ? 'REQUIRED' : 'PREFERRED',
})

const DATA_ANALYST: DiscoverItem = {
  job: {
    job_id: '00000000-0000-4000-8000-00000000b201',
    source: 'preview',
    title: 'Data Analyst Intern',
    company_name: 'DBS Bank',
    location: 'Singapore',
    job_type: 'INTERNSHIP',
    work_arrangement: 'HYBRID',
    application_url: 'https://example.test/jobs/data-analyst-intern',
    source_posted_at: '2026-10-21T00:00:00Z',
    is_active: true,
  },
  match: {
    required_total: 5,
    required_matched: 3,
    preferred_total: 2,
    preferred_matched: 1,
    coverage: 0.6,
    matched_skills: [skill(1, 'SQL', true), skill(2, 'Python', true), skill(3, 'Microsoft Excel', true), skill(4, 'Data Visualization', false)],
    missing_skills: [skill(5, 'Statistics', true), skill(6, 'Tableau', true), skill(7, 'Power BI', false)],
  },
  rank: 1,
}

const AIRPORT_OPS: DiscoverItem = {
  job: {
    job_id: '00000000-0000-4000-8000-00000000b2d4',
    source: 'preview',
    title: 'Airport Operations Intern',
    company_name: 'Changi Airport Group',
    location: 'Changi, Singapore',
    job_type: 'INTERNSHIP',
    work_arrangement: 'ONSITE',
    application_url: 'https://example.test/jobs/airport-operations-intern',
    source_posted_at: '2026-10-19T00:00:00Z',
    is_active: true,
  },
  match: {
    required_total: 0,
    required_matched: 0,
    preferred_total: 0,
    preferred_matched: 0,
    coverage: null,
    matched_skills: [],
    missing_skills: [],
  },
  rank: 212,
}

const FOLLOWING: Array<[string, string]> = [
  ['UX Research Intern', 'Grab'], ['Software Engineer Intern', 'GovTech'], ['Business Analyst Intern', 'OCBC'],
  ['Marketing Analytics Intern', 'Shopee'], ['Product Operations Intern', 'Carousell'], ['Risk Analyst Intern', 'UOB'],
  ['Data Engineering Intern', 'Sea'], ['Finance Intern', 'Singtel'], ['Supply Chain Intern', 'Lazada'],
  ['Research Assistant', 'A*STAR'], ['Customer Insights Intern', 'NTUC FairPrice'], ['QA Engineer Intern', 'PropertyGuru'],
  ['Growth Intern', 'Ninja Van'], ['Operations Analyst Intern', 'PSA'], ['IT Support Intern', 'NUS'],
  ['Strategy Intern', 'Temasek'], ['HR Analytics Intern', 'SIA'], ['Frontend Intern', 'Razer'], ['Data Science Intern', 'Grab'],
]

/** The ready feed: the hand-off card first, then 19 more so the head reads "20 postings". */
const READY_FEED: DiscoverItem[] = [
  DATA_ANALYST,
  ...FOLLOWING.map(([title, company], index): DiscoverItem => ({
    ...DATA_ANALYST,
    job: { ...DATA_ANALYST.job, job_id: `00000000-0000-4000-8000-0000000b2${String(index + 10).padStart(3, '0')}`, title, company_name: company },
    rank: index + 2,
  })),
]

const wait = (ms: number) => new Promise(resolve => window.setTimeout(resolve, ms))

function feedClient(items: DiscoverItem[], decide: DiscoverClient['decide'] = async () => { await wait(90) }): DiscoverClient {
  return {
    async list(_filters, offset, limit) {
      await wait(60)
      return { items: items.slice(offset, offset + limit), has_more: items.length > offset + limit }
    },
    decide,
  }
}

const neverResolves: DiscoverClient = {
  list: () => new Promise(() => {}),
  decide: () => new Promise(() => {}),
}

const failingDecisions = feedClient(READY_FEED, async () => {
  await wait(60)
  throw { status: 503, code: 'service_unavailable', message: 'Service unavailable' }
})

const profileMissing: DiscoverClient = {
  async list() {
    await wait(40)
    throw { status: 404, code: 'not_found', message: 'Profile not found', details: { resource: 'profile' } }
  },
  decide: async () => {},
}

/* ------------------------------------------------------------------ scene helpers */

function InShell({ content }: { content: ReactNode }) {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="*" element={content} />
      </Route>
    </Routes>
  )
}

/** Sets a React-controlled field the way typing would. */
function setFieldValue(id: string, value: string) {
  const element = document.getElementById(id) as HTMLInputElement | HTMLSelectElement | null
  if (!element) return
  const proto = element instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype
  Object.getOwnPropertyDescriptor(proto, 'value')?.set?.call(element, value)
  element.dispatchEvent(new Event(element instanceof HTMLSelectElement ? 'change' : 'input', { bubbles: true }))
}

/** Runs `step` every 20ms until it returns true (or gives up), to stage a state after mount. */
function Stage({ step, children }: { step: () => boolean; children: ReactNode }) {
  useEffect(() => {
    let tries = 0
    const timer = window.setInterval(() => {
      tries += 1
      if (step() || tries > 100) window.clearInterval(timer)
    }, 20)
    return () => window.clearInterval(timer)
  }, [step])
  return <>{children}</>
}

const editFilters = () => {
  if (!document.querySelector('[data-primary]')) return false
  setFieldValue('discover-keyword', 'data')
  setFieldValue('discover-job-type', 'INTERNSHIP')
  setFieldValue('discover-location', 'Jurong')
  document.getElementById('discover-location')?.focus()
  return true
}

const openSheetAndEdit = () => {
  if (!document.querySelector('[data-primary]')) return false
  document.querySelector<HTMLButtonElement>('[aria-haspopup="dialog"]')?.click()
  window.setTimeout(() => {
    setFieldValue('discover-job-type', 'INTERNSHIP')
    setFieldValue('discover-location', 'Jurong')
    document.getElementById('discover-location')?.focus()
  }, 30)
  return true
}

const clickSave = () => {
  const save = document.querySelector<HTMLButtonElement>('[data-primary]:not(:disabled)')
  save?.click()
  return Boolean(save)
}

const feed = (client: DiscoverClient) => <DiscoverFeed client={client} onProfileMissing={() => {}} />

/* ------------------------------------------------------------------ scenes */

export const b2Scenes: PreviewScene[] = [
  {
    id: 'discover-ready',
    title: 'Discover, ready (mobile: discover-mobile-ready)',
    group: GROUP,
    path: routes.discover,
    reference: 'discover-ready.png',
    element: <InShell content={feed(feedClient(READY_FEED))} />,
  },
  {
    id: 'discover-filters-edited',
    title: 'Discover, filters edited but not applied',
    group: GROUP,
    path: routes.discover,
    reference: 'discover-filters-edited.png',
    element: <InShell content={<Stage step={editFilters}>{feed(feedClient(READY_FEED))}</Stage>} />,
  },
  {
    id: 'discover-mobile-filters-sheet',
    title: 'Discover, mobile filter sheet open (desktop shows inline filters)',
    group: GROUP,
    path: routes.discover,
    reference: 'discover-mobile-filters-sheet.png',
    element: <InShell content={<Stage step={openSheetAndEdit}>{feed(feedClient(READY_FEED))}</Stage>} />,
  },
  {
    id: 'discover-no-requirements-extracted',
    title: 'Discover, posting with no extracted requirements',
    group: GROUP,
    path: routes.discover,
    reference: 'discover-no-requirements-extracted.png',
    element: <InShell content={feed(feedClient([AIRPORT_OPS]))} />,
  },
  {
    id: 'discover-loading',
    title: 'Discover, first page loading',
    group: GROUP,
    path: routes.discover,
    reference: 'discover-loading.png',
    element: <InShell content={feed(neverResolves)} />,
  },
  {
    id: 'discover-decision-failed',
    title: 'Discover, save failed and rolled back (mobile: discover-mobile-decision-failed)',
    group: GROUP,
    path: routes.discover,
    reference: 'discover-decision-failed.png',
    element: <InShell content={<Stage step={clickSave}>{feed(failingDecisions)}</Stage>} />,
  },
  {
    id: 'discover-empty-feed',
    title: 'Discover, nothing left for the filters (mobile: discover-mobile-empty-feed)',
    group: GROUP,
    path: `${routes.discover}?job_type=INTERNSHIP&work_arrangement=REMOTE`,
    reference: 'discover-empty-feed.png',
    element: <InShell content={feed(feedClient([]))} />,
  },
  {
    id: 'discover-no-profile-redirect',
    title: 'Discover, profile missing (redirect to onboarding)',
    group: GROUP,
    path: routes.discover,
    reference: 'discover-no-profile-redirect.png',
    element: <main className="center-page">{feed(profileMissing)}</main>,
  },
]
