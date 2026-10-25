import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { TrackerClient } from './client'
import type { TrackerStatus } from './types'
import type { TrackerItem, TrackerSummary } from './types'
import { VaultScreen } from '../../screens/VaultScreen'

const JOB = {
  job_id: '00000000-0000-4000-8000-000000000001',
  title: 'Graduate Software Engineer',
  company_name: 'Example Labs',
  location: 'Singapore',
  job_type: 'FULL_TIME' as const,
  work_arrangement: 'HYBRID' as const,
  application_url: 'https://example.test/jobs/1',
  source: 'synthetic',
  source_posted_at: null,
  is_active: true,
}

function item(status: TrackerStatus = 'SAVED', id = JOB.job_id): TrackerItem {
  return {
    job: { ...JOB, job_id: id, title: id === JOB.job_id ? JOB.title : `Job ${id.slice(-2)}` },
    status,
    created_at: '2026-10-20T10:00:00Z',
    updated_at: '2026-10-25T10:00:00Z',
  }
}

function summary(overrides: Partial<Record<TrackerStatus, number>> = {}): TrackerSummary {
  return {
    counts: {
      NOT_INTERESTED: 2,
      SAVED: 1,
      APPLIED: 3,
      INTERVIEW: 0,
      REJECTED: 1,
      OFFER: 0,
      ...overrides,
    },
    total: 7,
  }
}

function fakeClient(overrides: Partial<TrackerClient> = {}): TrackerClient {
  return {
    summary: vi.fn(async () => summary()),
    list: vi.fn(async (status: TrackerStatus, _limit: number, _offset: number) => ({
      items: status === 'SAVED' ? [item()] : [],
      total: status === 'SAVED' ? 1 : 0,
    })),
    update: vi.fn(async (_jobId: string, status: TrackerStatus) => item(status)),
    remove: vi.fn(async () => undefined),
    ...overrides,
  }
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('VaultScreen', () => {
  it('loads status counts and opens the SAVED tab by default', async () => {
    const client = fakeClient()
    render(<VaultScreen client={client} />)

    expect(await screen.findByRole('heading', { name: 'Graduate Software Engineer' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Saved 1' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'Applied 3' })).toBeInTheDocument()
    expect(client.list).toHaveBeenCalledWith('SAVED', 20, 0)
  })

  it('moves a row after a successful status update and refreshes counts', async () => {
    let currentStatus: TrackerStatus = 'SAVED'
    let resolveUpdate!: (value: TrackerItem) => void
    const client = fakeClient({
      update: vi.fn((_jobId, status) => new Promise<TrackerItem>(resolve => {
        resolveUpdate = () => { currentStatus = status; resolve(item(status)) }
      })),
      list: vi.fn(async (status, _limit, _offset) => ({ items: status === currentStatus ? [item(currentStatus)] : [], total: status === currentStatus ? 1 : 0 })),
      summary: vi.fn(async () => summary({ SAVED: currentStatus === 'SAVED' ? 1 : 0, APPLIED: currentStatus === 'APPLIED' ? 4 : 3 })),
    })
    const user = userEvent.setup()
    render(<VaultScreen client={client} />)

    const row = await screen.findByRole('heading', { name: JOB.title }).then(node => node.closest('li')!)
    await user.selectOptions(within(row).getByRole('combobox', { name: /status/i }), 'APPLIED')

    await waitFor(() => expect(screen.queryByRole('heading', { name: JOB.title })).not.toBeInTheDocument())
    expect(screen.getByRole('tab', { name: 'Saved 0' })).toBeInTheDocument()
    await waitFor(() => expect(client.update).toHaveBeenCalledWith(JOB.job_id, 'APPLIED'))
    resolveUpdate(item('APPLIED'))
    expect(client.update).toHaveBeenCalledWith(JOB.job_id, 'APPLIED')
    expect(await screen.findByRole('tab', { name: 'Applied 4' })).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: 'Applied 4' }))
    expect(await screen.findByRole('heading', { name: JOB.title })).toBeInTheDocument()
  })

  it('restores the previous status and row when a status update fails', async () => {
    const client = fakeClient({
      update: vi.fn(async () => {
        throw { status: 503, code: 'service_unavailable', message: 'Could not save this status.' }
      }),
    })
    const user = userEvent.setup()
    render(<VaultScreen client={client} />)

    const row = await screen.findByRole('heading', { name: JOB.title }).then(node => node.closest('li')!)
    await user.selectOptions(within(row).getByRole('combobox', { name: /status/i }), 'APPLIED')

    expect(await screen.findByText('Could not save this status.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: JOB.title })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: /status/i })).toHaveValue('SAVED')
  })

  it('removes a row only after the confirmed DELETE completes', async () => {
    let removed = false
    const client = fakeClient({
      list: vi.fn(async (status, _limit, _offset) => ({ items: status === 'SAVED' && !removed ? [item()] : [], total: status === 'SAVED' && !removed ? 1 : 0 })),
      summary: vi.fn(async () => summary({ SAVED: removed ? 0 : 1 })),
      remove: vi.fn(async () => { removed = true }),
    })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const user = userEvent.setup()
    render(<VaultScreen client={client} />)

    const row = await screen.findByRole('heading', { name: JOB.title }).then(node => node.closest('li')!)
    await user.click(within(row).getByRole('button', { name: 'Remove' }))

    expect(confirm).toHaveBeenCalled()
    expect(client.remove).toHaveBeenCalledWith(JOB.job_id)
    await waitFor(() => expect(screen.queryByRole('heading', { name: JOB.title })).not.toBeInTheDocument())
    confirm.mockRestore()
  })

  it('ignores an older tab response that arrives after the current tab', async () => {
    let resolveSaved!: (value: { items: TrackerItem[]; total: number }) => void
    let firstRequest = true
    const client = fakeClient({
      list: vi.fn((tabStatus) => {
        if (tabStatus === 'SAVED' && firstRequest) {
          firstRequest = false
          return new Promise<{ items: TrackerItem[]; total: number }>(resolve => { resolveSaved = resolve })
        }
        return Promise.resolve({ items: [], total: 0 })
      }),
    })
    const user = userEvent.setup()
    render(<VaultScreen client={client} />)

    await user.click(screen.getByRole('tab', { name: 'Not interested 0' }))
    expect(await screen.findByText('No jobs in Not interested yet.')).toBeInTheDocument()
    await act(async () => resolveSaved({ items: [item()], total: 1 }))

    expect(screen.queryByRole('heading', { name: JOB.title })).not.toBeInTheDocument()
    expect(screen.getByText('No jobs in Not interested yet.')).toBeInTheDocument()
  })

  it('keeps a successful status write successful when its list refresh fails', async () => {
    let listCalls = 0
    const client = fakeClient({
      list: vi.fn(async (tabStatus) => {
        listCalls += 1
        if (listCalls > 1) throw { status: 503, code: 'service_unavailable', message: 'Refresh unavailable.' }
        return { items: tabStatus === 'SAVED' ? [item()] : [], total: tabStatus === 'SAVED' ? 1 : 0 }
      }),
      update: vi.fn(async (_jobId, nextStatus) => item(nextStatus)),
    })
    const user = userEvent.setup()
    render(<VaultScreen client={client} />)

    const row = await screen.findByRole('heading', { name: JOB.title }).then(node => node.closest('li')!)
    await user.selectOptions(within(row).getByRole('combobox', { name: /status/i }), 'APPLIED')

    expect(await screen.findByText('Status saved, but the view could not be refreshed. Reload to see the latest data.')).toBeInTheDocument()
    expect(screen.queryByText('Could not save this status.')).not.toBeInTheDocument()
    expect(client.update).toHaveBeenCalledWith(JOB.job_id, 'APPLIED')
  })

  it('paginates in pages of 20', async () => {
    const firstPage = Array.from({ length: 20 }, (_, index) => item('SAVED', `20000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`))
    const client = fakeClient({
      list: vi.fn(async (_status, _limit, offset) => ({
        items: offset === 0 ? firstPage : [item('SAVED', '00000000-0000-4000-8000-000000000021')],
        total: 21,
      })),
    })
    const user = userEvent.setup()
    render(<VaultScreen client={client} />)

    expect(await screen.findByRole('heading', { name: 'Job 01' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Next page' }))

    expect(await screen.findByRole('heading', { name: 'Job 21' })).toBeInTheDocument()
    expect(client.list).toHaveBeenLastCalledWith('SAVED', 20, 20)
    expect(screen.getByText('Page 2 of 2')).toBeInTheDocument()
  })

  it('shows an empty state for a status with no tracked jobs', async () => {
    const client = fakeClient()
    const user = userEvent.setup()
    render(<VaultScreen client={client} />)
    await screen.findByRole('heading', { name: JOB.title })

    await user.click(screen.getByRole('tab', { name: 'Interview 0' }))

    expect(await screen.findByText('No jobs in Interview yet.')).toBeInTheDocument()
  })
})
