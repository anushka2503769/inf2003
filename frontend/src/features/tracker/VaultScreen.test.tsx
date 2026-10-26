import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { TrackerClient } from './client'
import type { TrackerItem, TrackerStatus, TrackerSummary } from './types'
import { ApiError } from '../../lib/api-client'
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

function item(status: TrackerStatus = 'SAVED', id = JOB.job_id, isActive = true): TrackerItem {
  return {
    job: { ...JOB, job_id: id, is_active: isActive, title: id === JOB.job_id ? JOB.title : `Job ${id.slice(-2)}` },
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

  it('restores status and counts when a pending status update fails', async () => {
    let rejectUpdate!: (cause: unknown) => void
    const client = fakeClient({
      summary: vi.fn(async () => summary()),
      update: vi.fn(() => new Promise<TrackerItem>((_resolve, reject) => { rejectUpdate = reject })),
    })
    const user = userEvent.setup()
    render(<VaultScreen client={client} />)

    const row = await screen.findByRole('heading', { name: JOB.title }).then(node => node.closest('li')!)
    await user.selectOptions(within(row).getByRole('combobox', { name: /status/i }), 'APPLIED')

    expect(screen.getByRole('tab', { name: 'Saved 0' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Applied 4' })).toBeInTheDocument()
    expect(screen.getByText('No jobs in Saved yet.')).toBeInTheDocument()
    await act(async () => rejectUpdate(new ApiError(503, 'service_unavailable', 'Private backend detail.')))

    expect(await screen.findByText('The server had a problem with that request. Try again in a moment.')).toBeInTheDocument()
    expect(screen.queryByText('Private backend detail.')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: JOB.title })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: /status/i })).toHaveValue('SAVED')
    expect(screen.getByRole('tab', { name: 'Saved 1' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Applied 3' })).toBeInTheDocument()
  })

  it('lets the user cancel the accessible in-page removal confirmation', async () => {
    const client = fakeClient()
    const user = userEvent.setup()
    render(<VaultScreen client={client} />)

    const row = await screen.findByRole('heading', { name: JOB.title }).then(node => node.closest('li')!)
    await user.click(within(row).getByRole('button', { name: 'Remove' }))
    const confirmation = screen.getByRole('group', { name: /confirm removal/i })
    expect(within(confirmation).getByRole('button', { name: 'Cancel' })).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('group', { name: /confirm removal/i })).not.toBeInTheDocument()
    expect(within(row).getByRole('button', { name: 'Remove' })).toHaveFocus()

    await user.click(within(row).getByRole('button', { name: 'Remove' }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(client.remove).not.toHaveBeenCalled()
    expect(screen.getByRole('heading', { name: JOB.title })).toBeInTheDocument()
  })

  it('confirms removal in-page and removes the row after DELETE succeeds', async () => {
    let removed = false
    const client = fakeClient({
      list: vi.fn(async (tabStatus) => ({ items: tabStatus === 'SAVED' && !removed ? [item()] : [], total: tabStatus === 'SAVED' && !removed ? 1 : 0 })),
      summary: vi.fn(async () => summary({ SAVED: removed ? 0 : 1 })),
      remove: vi.fn(async () => { removed = true }),
    })
    const user = userEvent.setup()
    render(<VaultScreen client={client} />)

    const row = await screen.findByRole('heading', { name: JOB.title }).then(node => node.closest('li')!)
    await user.click(within(row).getByRole('button', { name: 'Remove' }))
    const confirmation = screen.getByRole('group', { name: /confirm removal/i })
    await user.click(within(confirmation).getByRole('button', { name: 'Remove' }))

    expect(client.remove).toHaveBeenCalledWith(JOB.job_id)
    await waitFor(() => expect(screen.queryByRole('heading', { name: JOB.title })).not.toBeInTheDocument())
    expect(screen.queryByRole('group', { name: /confirm removal/i })).not.toBeInTheDocument()
  })

  it('keeps the row and confirmation open when DELETE fails', async () => {
    const client = fakeClient({
      remove: vi.fn(async () => { throw new ApiError(503, 'service_unavailable', 'Private delete detail.') }),
    })
    const user = userEvent.setup()
    render(<VaultScreen client={client} />)

    const row = await screen.findByRole('heading', { name: JOB.title }).then(node => node.closest('li')!)
    await user.click(within(row).getByRole('button', { name: 'Remove' }))
    const confirmation = screen.getByRole('group', { name: /confirm removal/i })
    await user.click(within(confirmation).getByRole('button', { name: 'Remove' }))

    expect(await screen.findByText('The server had a problem with that request. Try again in a moment.')).toBeInTheDocument()
    expect(screen.queryByText('Private delete detail.')).not.toBeInTheDocument()
    expect(screen.getByRole('group', { name: /confirm removal/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: JOB.title })).toBeInTheDocument()
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

  it('renders all six status tabs with their count and linked tab panel', async () => {
    const user = userEvent.setup()
    render(<VaultScreen client={fakeClient()} />)

    const expected = ['Not interested 2', 'Saved 1', 'Applied 3', 'Interview 0', 'Rejected 1', 'Offer 0']
    expect(await screen.findByRole('tab', { name: expected[0] })).toBeInTheDocument()
    for (const name of expected) expect(screen.getByRole('tab', { name })).toBeInTheDocument()
    const saved = screen.getByRole('tab', { name: 'Saved 1' })
    const panel = screen.getByRole('tabpanel')
    expect(saved).toHaveAttribute('aria-controls', panel.id)
    expect(panel).toHaveAttribute('aria-labelledby', saved.id)

    await user.click(saved)
    await user.keyboard('{ArrowRight}')
    const applied = screen.getByRole('tab', { name: 'Applied 3' })
    expect(applied).toHaveFocus()
    expect(applied).toHaveAttribute('aria-selected', 'true')
    expect(panel).toHaveAttribute('aria-labelledby', applied.id)
    await user.keyboard('{ArrowLeft}')
    expect(saved).toHaveFocus()
    expect(saved).toHaveAttribute('aria-selected', 'true')
    expect(panel).toHaveAttribute('aria-labelledby', saved.id)
  })

  it('steps back and reloads the prior page when changing the only row on the last page', async () => {
    const firstPage = Array.from({ length: 20 }, (_, index) => item('SAVED', `30000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`))
    let changed = false
    const client = fakeClient({
      list: vi.fn(async (tabStatus, _limit, offset) => {
        if (tabStatus !== 'SAVED') return { items: [], total: 0 }
        if (offset === 0) return { items: firstPage, total: changed ? 20 : 21 }
        return { items: changed ? [] : [item('SAVED', '30000000-0000-4000-8000-000000000021')], total: changed ? 20 : 21 }
      }),
      update: vi.fn(async (_jobId, nextStatus) => { changed = true; return item(nextStatus, '30000000-0000-4000-8000-000000000021') }),
    })
    const user = userEvent.setup()
    render(<VaultScreen client={client} />)
    await user.click(await screen.findByRole('button', { name: 'Next page' }))
    const row = await screen.findByRole('heading', { name: 'Job 21' }).then(node => node.closest('li')!)
    await user.selectOptions(within(row).getByRole('combobox', { name: /status/i }), 'APPLIED')

    expect(await screen.findByRole('heading', { name: 'Job 20' })).toBeInTheDocument()
    expect(client.list).toHaveBeenLastCalledWith('SAVED', 20, 0)
    expect(screen.queryByText('Page 2 of 2')).not.toBeInTheDocument()
  })

  it('disables both page controls while a status update is pending', async () => {
    const allRows = Array.from({ length: 42 }, (_, index) => item('SAVED', `40000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`))
    let finishUpdate!: () => void
    const client = fakeClient({
      list: vi.fn(async (_tabStatus, _limit, offset) => ({ items: allRows.slice(offset, offset + 20), total: 42 })),
      update: vi.fn((jobId, nextStatus) => new Promise<TrackerItem>(resolve => { finishUpdate = () => resolve(item(nextStatus, jobId)) })),
    })
    const user = userEvent.setup()
    render(<VaultScreen client={client} />)
    await user.click(await screen.findByRole('button', { name: 'Next page' }))
    await screen.findByRole('heading', { name: 'Job 21' })
    const row = screen.getByRole('heading', { name: 'Job 21' }).closest('li')!
    await user.selectOptions(within(row).getByRole('combobox', { name: /status/i }), 'APPLIED')

    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled()
    await act(async () => finishUpdate())
  })

  it('disables both page controls while DELETE is pending', async () => {
    const allRows = Array.from({ length: 42 }, (_, index) => item('SAVED', `50000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`))
    let removed = false
    let finishDelete!: () => void
    const client = fakeClient({
      list: vi.fn(async (_tabStatus, _limit, offset) => ({ items: allRows.slice(offset, offset + 20), total: removed ? 41 : 42 })),
      remove: vi.fn(() => new Promise<void>(resolve => { finishDelete = () => { removed = true; resolve() } })),
    })
    const user = userEvent.setup()
    render(<VaultScreen client={client} />)
    await user.click(await screen.findByRole('button', { name: 'Next page' }))
    await screen.findByRole('heading', { name: 'Job 21' })
    const row = screen.getByRole('heading', { name: 'Job 21' }).closest('li')!
    await user.click(within(row).getByRole('button', { name: 'Remove' }))
    const confirmation = screen.getByRole('group', { name: /confirm removal/i })
    await user.click(within(confirmation).getByRole('button', { name: 'Remove' }))

    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled()
    await act(async () => finishDelete())
  })

  it('shows the empty state as soon as the active page has no visible rows', async () => {
    let finishUpdate!: () => void
    const client = fakeClient({
      update: vi.fn((jobId, nextStatus) => new Promise<TrackerItem>(resolve => { finishUpdate = () => resolve(item(nextStatus, jobId)) })),
    })
    const user = userEvent.setup()
    render(<VaultScreen client={client} />)
    const row = await screen.findByRole('heading', { name: JOB.title }).then(node => node.closest('li')!)
    await user.selectOptions(within(row).getByRole('combobox', { name: /status/i }), 'APPLIED')

    expect(screen.getByText('No jobs in Saved yet.')).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Saved jobs' })).not.toBeInTheDocument()
    await act(async () => finishUpdate())
  })

  it('does not render a posting link for an unsafe application URL', async () => {
    const client = fakeClient({ list: vi.fn(async () => ({ items: [item('SAVED', JOB.job_id, true)], total: 1 })) })
    const unsafe = item()
    unsafe.job.application_url = 'javascript:alert(1)'
    client.list = vi.fn(async () => ({ items: [unsafe], total: 1 }))
    render(<VaultScreen client={client} />)

    await screen.findByRole('heading', { name: JOB.title })
    expect(screen.queryByRole('link', { name: 'Open posting' })).not.toBeInTheDocument()
  })

  it('labels inactive jobs while keeping their status selector available', async () => {
    const inactive = item('SAVED', JOB.job_id, false)
    const client = fakeClient({ list: vi.fn(async () => ({ items: [inactive], total: 1 })) })
    render(<VaultScreen client={client} />)

    const row = await screen.findByRole('heading', { name: JOB.title }).then(node => node.closest('li')!)
    expect(within(row).getByText('No longer listed')).toBeInTheDocument()
    expect(within(row).getByRole('combobox', { name: /status/i })).toBeEnabled()
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

  it('exposes the status tabs, not the mobile "Show" dropdown, on desktop', async () => {
    render(<VaultScreen client={fakeClient()} />)

    expect(await screen.findByRole('tablist', { name: 'Tracker status' })).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Show' })).not.toBeInTheDocument()
    expect(screen.getByRole('tabpanel')).toBeInTheDocument()
  })

  it('replaces the tabs with a labelled "Show" dropdown on mobile', async () => {
    const original = window.matchMedia
    window.matchMedia = vi.fn((query: string) => ({
      matches: query.includes('max-width'),
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(() => false),
    })) as unknown as typeof window.matchMedia
    try {
      const client = fakeClient()
      const user = userEvent.setup()
      render(<VaultScreen client={client} />)

      await screen.findByRole('heading', { name: JOB.title })
      expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
      expect(screen.queryByRole('tab')).not.toBeInTheDocument()
      const show = screen.getByRole('combobox', { name: 'Show' })
      expect(show).toHaveValue('SAVED')
      expect(within(show).getByRole('option', { name: 'Applied (3)' })).toBeInTheDocument()
      expect(screen.getByRole('region', { name: 'Saved jobs' })).toBeInTheDocument()

      await user.selectOptions(show, 'APPLIED')
      expect(client.list).toHaveBeenLastCalledWith('APPLIED', 20, 0)
      expect(await screen.findByText('No jobs in Applied yet.')).toBeInTheDocument()
    } finally {
      window.matchMedia = original
    }
  })
})
