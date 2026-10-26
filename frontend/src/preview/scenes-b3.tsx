import { useEffect, type ReactNode } from 'react'
import { Route, Routes } from 'react-router-dom'

import { AppShell } from '../app/AppShell'
import { routes } from '../app/routes'
import type { TrackerClient } from '../features/tracker/client'
import type { TrackerItem, TrackerStatus } from '../features/tracker/types'
import { ApiError } from '../lib/api-client'
import { VaultScreen } from '../screens/VaultScreen'
import type { PreviewScene } from './types'

/** Preview scenes for Vault (redesign B3). Fake tracker data mirrors the hand-off rows. */

const GROUP = 'B3 Vault'

/* ------------------------------------------------------------------ fake data */

const COUNTS: Record<TrackerStatus, number> = {
  SAVED: 47,
  APPLIED: 12,
  INTERVIEW: 3,
  OFFER: 0,
  REJECTED: 5,
  NOT_INTERESTED: 86,
}

type RowSeed = [title: string, company: string, location: string, updated: string, active?: boolean]

const SAVED_ROWS: RowSeed[] = [
  ['Data Analyst Intern', 'DBS Bank', 'Singapore', '2026-10-24'],
  ['UX Research Intern', 'Grab', 'One-north', '2026-10-23'],
  ['Software Engineer Intern (Backend)', 'GovTech', 'Singapore', '2026-10-22'],
  ['Business Analyst Intern', 'OCBC', 'Singapore', '2026-10-20', false],
  ['Product Management Intern', 'Carousell', 'Singapore', '2026-10-18'],
  ['Supply Chain Analytics Intern', 'PSA International', 'Pasir Panjang', '2026-10-15'],
  ['Marketing Intern', 'Shopee', 'Singapore', '2026-10-11'],
]

const APPLIED_ROWS: RowSeed[] = [
  ['UX Research Intern', 'Grab', 'One-north', '2026-10-25'],
  ['Data Engineering Intern', 'Sea', 'Singapore', '2026-10-19'],
  ['Cybersecurity Intern', 'ST Engineering', 'Ang Mo Kio', '2026-10-12'],
  ['Risk Analyst Intern', 'Singtel', 'Singapore', '2026-10-03', false],
]

const FILLER: Array<[string, string]> = [
  ['Finance Intern', 'UOB'],
  ['Operations Intern', 'SATS'],
  ['HR Analytics Intern', 'Singapore Airlines'],
  ['Quant Research Intern', 'GIC'],
  ['Frontend Engineer Intern', 'Ninja Van'],
  ['Data Science Intern', 'Lazada'],
]

let idCounter = 0
function trackerItem(status: TrackerStatus, [title, company, location, updated, active = true]: RowSeed): TrackerItem {
  idCounter += 1
  const suffix = String(idCounter).padStart(12, '0')
  return {
    job: {
      job_id: `b3000000-0000-4000-8000-${suffix}`,
      title,
      company_name: company,
      location,
      job_type: 'INTERNSHIP',
      work_arrangement: 'HYBRID',
      // A closed posting has no usable link here, so the row shows "Posting closed".
      application_url: active ? `https://careers.example.test/${suffix}` : '',
      source: 'preview',
      source_posted_at: null,
      is_active: active,
    },
    status,
    created_at: `${updated}T02:00:00Z`,
    updated_at: `${updated}T02:00:00Z`,
  }
}

/** COUNTS[status] items; the hand-off rows start at `rowsAt` so a scene can page to them. */
function itemsFor(status: TrackerStatus, seeds: RowSeed[], rowsAt: number): TrackerItem[] {
  return Array.from({ length: COUNTS[status] }, (_, index) => {
    const seed = seeds[index - rowsAt]
    if (seed) return trackerItem(status, seed)
    const [title, company] = FILLER[index % FILLER.length]
    return trackerItem(status, [title, company, 'Singapore', '2026-09-30'])
  })
}

const ITEMS: Record<TrackerStatus, TrackerItem[]> = {
  SAVED: itemsFor('SAVED', SAVED_ROWS, 40),
  APPLIED: itemsFor('APPLIED', APPLIED_ROWS, 0),
  INTERVIEW: itemsFor('INTERVIEW', [], 0),
  OFFER: [],
  REJECTED: itemsFor('REJECTED', [], 0),
  NOT_INTERESTED: itemsFor('NOT_INTERESTED', [], 0),
}

function single(status: TrackerStatus | readonly TrackerStatus[] | undefined): TrackerStatus {
  if (typeof status === 'string') return status
  return status?.[0] ?? 'SAVED'
}

function fakeTrackerClient({ loading = false, failUpdates = false } = {}): TrackerClient {
  return {
    summary: async () => ({ counts: { ...COUNTS }, total: Object.values(COUNTS).reduce((a, b) => a + b, 0) }),
    list: (status, limit, offset) => {
      if (loading) return new Promise(() => {})
      const items = ITEMS[single(status)]
      return Promise.resolve({ items: items.slice(offset, offset + limit), total: items.length })
    },
    update: async (jobId, status) => {
      if (failUpdates) throw new ApiError(0, 'network_error', 'Network request failed.')
      const found = Object.values(ITEMS).flat().find(item => item.job.job_id === jobId)
      if (!found) throw new ApiError(404, 'not_found', 'Not found.')
      return { ...found, status }
    },
    remove: async () => undefined,
  }
}

/* ------------------------------------------------------------------ scene drivers */

type Step = () => boolean

/** Runs each step in turn, polling until it reports done, so a scene can open a state after load. */
function Driver({ steps, children }: { steps: Step[]; children: ReactNode }) {
  useEffect(() => {
    let index = 0
    const timer = window.setInterval(() => {
      while (index < steps.length && steps[index]()) index += 1
      if (index >= steps.length) window.clearInterval(timer)
    }, 10)
    return () => window.clearInterval(timer)
  }, [steps])
  return <>{children}</>
}

function waitForPager(text: string): Step {
  return () => document.querySelector('.vault__pager')?.textContent?.includes(text) ?? false
}

function waitForRow(title: string): Step {
  return () => document.querySelector(`select[aria-label="Status for ${title}"]`) !== null
}

function click(selector: string): Step {
  return () => {
    const target = document.querySelector<HTMLButtonElement>(selector)
    if (!target || target.disabled) return false
    target.click()
    return true
  }
}

function setStatusOf(title: string, value: TrackerStatus): Step {
  return () => {
    const select = document.querySelector<HTMLSelectElement>(`select[aria-label="Status for ${title}"]`)
    if (!select || select.disabled) return false
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')?.set?.call(select, value)
    select.dispatchEvent(new Event('change', { bubbles: true }))
    return true
  }
}

function focusSelectOf(title: string): Step {
  return () => {
    const select = document.querySelector<HTMLSelectElement>(`select[aria-label="Status for ${title}"]`)
    select?.focus()
    return select !== null
  }
}

const loaded = waitForPager('1–20 of 47')

const toLastSavedPage: Step[] = [
  loaded,
  click('button[aria-label="Next page"]'),
  waitForPager('21–40 of 47'),
  click('button[aria-label="Next page"]'),
  waitForPager('41–47 of 47'),
  waitForRow('Data Analyst Intern'),
]

function vault(client: TrackerClient, steps: Step[] = []) {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route
          path="*"
          element={
            <Driver steps={steps}>
              <VaultScreen client={client} />
            </Driver>
          }
        />
      </Route>
    </Routes>
  )
}

export const b3Scenes: PreviewScene[] = [
  {
    id: 'vault-saved',
    title: 'Vault, Saved tab (last page)',
    group: GROUP,
    path: routes.vault,
    reference: 'vault-saved.png',
    element: vault(fakeTrackerClient(), toLastSavedPage),
  },
  {
    id: 'vault-status-focused',
    title: 'Vault, status select focused (the native menu itself cannot be captured)',
    group: GROUP,
    path: routes.vault,
    reference: 'vault-status-menu-open.png',
    element: vault(fakeTrackerClient(), [...toLastSavedPage, focusSelectOf('UX Research Intern')]),
  },
  {
    id: 'vault-status-change-failed',
    title: 'Vault, status change failed and rolled back',
    group: GROUP,
    path: routes.vault,
    reference: 'vault-status-change-failed.png',
    element: vault(fakeTrackerClient({ failUpdates: true }), [
      loaded,
      click('#vault-tab-applied'),
      waitForRow('Cybersecurity Intern'),
      setStatusOf('UX Research Intern', 'INTERVIEW'),
    ]),
  },
  {
    id: 'vault-remove-confirmation',
    title: 'Vault, in-page remove confirmation',
    group: GROUP,
    path: routes.vault,
    reference: 'vault-remove-confirmation.png',
    element: vault(fakeTrackerClient(), [
      ...toLastSavedPage,
      click('button[title="Remove Software Engineer Intern (Backend)"]'),
    ]),
  },
  {
    id: 'vault-empty-tab',
    title: 'Vault, empty tab (Offer)',
    group: GROUP,
    path: routes.vault,
    reference: 'vault-empty-tab.png',
    element: vault(fakeTrackerClient(), [loaded, click('#vault-tab-offer')]),
  },
  {
    id: 'vault-loading',
    title: 'Vault, loading',
    group: GROUP,
    path: routes.vault,
    reference: 'vault-loading.png',
    element: vault(fakeTrackerClient({ loading: true })),
  },
]
