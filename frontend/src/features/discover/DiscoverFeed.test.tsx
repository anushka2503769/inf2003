import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, useLocation } from 'react-router-dom'

import { DiscoverFeed } from './DiscoverFeed'
import type { DiscoverClient } from './client'
import type { DiscoverItem, DiscoverResponse } from './types'

const JOB: DiscoverItem = {
  job: {
    job_id: '00000000-0000-4000-8000-000000000001', source: 'fixture', title: 'Junior Developer',
    company_name: 'Paper Co', location: 'Singapore', job_type: 'INTERNSHIP',
    work_arrangement: 'HYBRID', application_url: 'https://example.test/apply',
    source_posted_at: '2026-10-01T00:00:00Z', is_active: true,
  },
  match: {
    required_total: 2, required_matched: 1, preferred_total: 1, preferred_matched: 0,
    coverage: 0.5,
    matched_skills: [
      { skill_id: 3, name: 'Docker', requirement_type: 'PREFERRED' },
      { skill_id: 1, name: 'Python', requirement_type: 'REQUIRED' },
    ],
    missing_skills: [
      { skill_id: 3, name: 'Docker', requirement_type: 'PREFERRED' },
      { skill_id: 2, name: 'SQL', requirement_type: 'REQUIRED' },
    ],
  },
  rank: 1,
}

function makeClient(overrides: Partial<DiscoverClient> = {}): DiscoverClient {
  return {
    list: vi.fn(async (): Promise<DiscoverResponse> => ({ items: [JOB], has_more: false })),
    decide: vi.fn(async () => undefined),
    ...overrides,
  }
}

function LocationText() {
  const location = useLocation()
  return <output aria-label="Current URL">{location.search}</output>
}

function renderFeed(client: DiscoverClient, initialEntry = '/discover') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <DiscoverFeed client={client} />
      <LocationText />
    </MemoryRouter>,
  )
}

afterEach(() => cleanup())

describe('DiscoverFeed', () => {
  it('renders contract fields, required skills first, coverage, and posting link', async () => {
    renderFeed(makeClient())

    expect(await screen.findByRole('heading', { name: 'Junior Developer' })).toBeInTheDocument()
    expect(screen.getByText('You have 1 of 2 required skills')).toBeInTheDocument()
    const missing = screen.getByLabelText('Missing skills')
    expect(within(missing).getAllByRole('listitem').map(item => item.textContent?.split(' ·')[0])).toEqual(['SQL', 'Docker'])
    expect(screen.getByRole('link', { name: 'Open posting' })).toHaveAttribute('target', '_blank')
    expect(screen.getByRole('link', { name: 'Open posting' })).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('applies submitted filters to the URL and requests only the submitted values', async () => {
    const client = makeClient()
    const user = userEvent.setup()
    renderFeed(client)

    await user.selectOptions(screen.getByLabelText('Job type'), 'INTERNSHIP')
    await user.selectOptions(screen.getByLabelText('Work arrangement'), 'HYBRID')
    await user.type(screen.getByLabelText('Location'), 'Singapore')
    await user.type(screen.getByLabelText('Keyword'), 'developer')
    expect(client.list).toHaveBeenCalledWith({}, 0, 20)

    await user.click(screen.getByRole('button', { name: 'Apply filters' }))
    await waitFor(() => expect(client.list).toHaveBeenLastCalledWith(
      { job_type: 'INTERNSHIP', work_arrangement: 'HYBRID', location: 'Singapore', q: 'developer' }, 0, 20,
    ))
    expect(screen.getByLabelText('Current URL')).toHaveTextContent('job_type=INTERNSHIP')
    expect(screen.getByLabelText('Current URL')).toHaveTextContent('location=Singapore')
  })

  it('ignores arrow shortcuts while typing, and saves with ArrowRight elsewhere', async () => {
    const client = makeClient()
    renderFeed(client)
    await screen.findByRole('heading', { name: 'Junior Developer' })

    const keyword = screen.getByLabelText('Keyword')
    await userEvent.click(keyword)
    await userEvent.keyboard('{ArrowRight}')
    expect(client.decide).not.toHaveBeenCalled()

    await userEvent.click(screen.getByLabelText('Discover jobs'))
    await userEvent.keyboard('{ArrowRight}')
    await waitFor(() => expect(client.decide).toHaveBeenCalledWith(JOB.job.job_id, 'SAVED'))
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Junior Developer' })).not.toBeInTheDocument())
  })

  it('removes the card optimistically before the decision request resolves and handles ArrowLeft', async () => {
    let resolveDecision!: () => void
    const decide = vi.fn(() => new Promise<void>(resolve => { resolveDecision = resolve }))
    const client = makeClient({ decide })
    renderFeed(client)
    await screen.findByRole('heading', { name: 'Junior Developer' })

    await userEvent.click(screen.getByLabelText('Discover jobs'))
    await userEvent.keyboard('{ArrowLeft}')
    expect(client.decide).toHaveBeenCalledWith(JOB.job.job_id, 'NOT_INTERESTED')
    expect(screen.queryByRole('heading', { name: 'Junior Developer' })).not.toBeInTheDocument()
    await act(async () => resolveDecision())
  })

  it('restores a failed decision inline and retries the same decision', async () => {
    const decide = vi.fn<DiscoverClient['decide']>()
      .mockRejectedValueOnce({ status: 503, code: 'service_unavailable', message: 'Try again' })
      .mockResolvedValueOnce(undefined)
    const client = makeClient({ decide })
    const user = userEvent.setup()
    renderFeed(client)
    await user.click(await screen.findByRole('button', { name: 'Save' }))

    expect(await screen.findByText('Not saved — retry')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Junior Developer' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Not saved — retry' }))
    await waitFor(() => expect(decide).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Junior Developer' })).not.toBeInTheDocument())
  })

  it('shows the null coverage copy and the empty state actions', async () => {
    const noRequirements = { ...JOB, match: { ...JOB.match, required_total: 0, required_matched: 0, coverage: null } }
    const client = makeClient({ list: vi.fn(async () => ({ items: [{ ...noRequirements }], has_more: false })) })
    renderFeed(client)
    expect(await screen.findByText('No skill requirements were extracted for this job.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('No more jobs for these filters')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Change filters' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Check again' })).toBeInTheDocument()
  })

  it('waits for a decision to commit before prefetching the shifted server page', async () => {
    const items = Array.from({ length: 6 }, (_, index) => ({
      ...JOB, job: { ...JOB.job, job_id: `00000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`, title: `Test role ${index + 1}` },
    }))
    let serverItems = [...items]
    let resolveDecision!: () => void
    const list = vi.fn<DiscoverClient['list']>(async (_filters, offset) => ({
      items: serverItems.slice(offset, offset + (offset === 0 ? 4 : 20)), has_more: serverItems.length > offset + (offset === 0 ? 4 : 20),
    }))
    const client = makeClient({
      list,
      decide: vi.fn(async id => new Promise<void>(resolve => {
        resolveDecision = () => { serverItems = serverItems.filter(item => item.job.job_id !== id); resolve() }
      })),
    })
    renderFeed(client)

    await screen.findByRole('heading', { name: 'Test role 1' })
    await userEvent.click(screen.getAllByRole('button', { name: 'Save' })[0])
    expect(list).toHaveBeenCalledTimes(1)
    await act(async () => resolveDecision())
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2))
    expect(list).toHaveBeenLastCalledWith({}, 3, 20)
    expect(await screen.findByRole('heading', { name: 'Test role 5' })).toBeInTheDocument()
  })


  it('restarts an in-flight prefetch when the last visible card is decided', async () => {
    const next = { ...JOB, job: { ...JOB.job, job_id: '00000000-0000-4000-8000-000000000011', title: 'Next job' } }
    let serverItems = [JOB, next]
    let resolveOldPage!: (value: DiscoverResponse) => void
    const stalePage = new Promise<DiscoverResponse>(resolve => { resolveOldPage = resolve })
    let call = 0
    const list = vi.fn<DiscoverClient['list']>(async (_filters, offset) => {
      call += 1
      if (call === 1) return { items: [JOB], has_more: true }
      if (call === 2) return stalePage
      return { items: serverItems.slice(offset), has_more: false }
    })
    const client = makeClient({
      list,
      decide: vi.fn(async id => { serverItems = serverItems.filter(item => item.job.job_id !== id) }),
    })
    renderFeed(client)
    await screen.findByRole('heading', { name: 'Junior Developer' })
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2))
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('heading', { name: 'Next job' })).toBeInTheDocument()
    expect(list).toHaveBeenLastCalledWith({}, 0, 20)
    await act(async () => resolveOldPage({ items: [next], has_more: false }))
    expect(screen.getAllByRole('heading', { name: 'Next job' })).toHaveLength(1)
  })

  it('preserves loaded cards when prefetch fails and offers a manual retry', async () => {
    const items = Array.from({ length: 4 }, (_, index) => ({
      ...JOB, job: { ...JOB.job, job_id: `00000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`, title: `Retry role ${index + 1}` },
    }))
    const list = vi.fn<DiscoverClient['list']>()
      .mockResolvedValueOnce({ items, has_more: true })
      .mockRejectedValueOnce({ code: 'service_unavailable', status: 503 })
      .mockResolvedValueOnce({ items: [], has_more: false })
    renderFeed(makeClient({ list }))
    await screen.findByRole('heading', { name: 'Retry role 1' })
    await userEvent.click(screen.getAllByRole('button', { name: 'Save' })[0])
    expect(await screen.findByText('The server had a problem loading jobs. Try again in a moment.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Retry role 2' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Try loading more' }))
    await waitFor(() => expect(list).toHaveBeenCalledTimes(3))
  })


  it('ignores a response from filters that were replaced while it was loading', async () => {
    let resolveFirst!: (value: DiscoverResponse) => void
    const first = new Promise<DiscoverResponse>(resolve => { resolveFirst = resolve })
    const current = { ...JOB, job: { ...JOB.job, job_id: '00000000-0000-4000-8000-000000000009', title: 'Current filter role' } }
    const list = vi.fn<DiscoverClient['list']>()
      .mockReturnValueOnce(first)
      .mockResolvedValueOnce({ items: [current], has_more: false })
    const user = userEvent.setup()
    renderFeed(makeClient({ list }))

    await user.type(screen.getByLabelText('Location'), 'Remote')
    await user.click(screen.getByRole('button', { name: 'Apply filters' }))
    expect(await screen.findByRole('heading', { name: 'Current filter role' })).toBeInTheDocument()
    await act(async () => resolveFirst({ items: [JOB], has_more: false }))
    expect(screen.queryByRole('heading', { name: 'Junior Developer' })).not.toBeInTheDocument()
  })

  it('does not restore a failed decision into a newer filter result', async () => {
    let rejectDecision!: (error: Error) => void
    const decision = new Promise<void>((_resolve, reject) => { rejectDecision = reject })
    const current = { ...JOB, job: { ...JOB.job, job_id: '00000000-0000-4000-8000-000000000010', title: 'Current filter role' } }
    const list = vi.fn<DiscoverClient['list']>()
      .mockResolvedValueOnce({ items: [JOB], has_more: false })
      .mockResolvedValueOnce({ items: [current], has_more: false })
    const user = userEvent.setup()
    renderFeed(makeClient({ list, decide: vi.fn(() => decision) }))

    await user.click(await screen.findByRole('button', { name: 'Save' }))
    await user.type(screen.getByLabelText('Location'), 'Remote')
    await user.click(screen.getByRole('button', { name: 'Apply filters' }))
    expect(await screen.findByRole('heading', { name: 'Current filter role' })).toBeInTheDocument()
    await act(async () => rejectDecision(new Error('offline')))
    expect(screen.queryByRole('heading', { name: 'Junior Developer' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Current filter role' })).toBeInTheDocument()
  })

  it('refreshes profile state when Discover reports a missing profile', async () => {
    const client = makeClient({ list: vi.fn(async () => { throw { code: 'not_found', details: { resource: 'profile' } } }) })
    const reload = vi.fn()
    render(<MemoryRouter><DiscoverFeed client={client} onProfileMissing={reload} /></MemoryRouter>)
    await waitFor(() => expect(reload).toHaveBeenCalledTimes(1))
  })
})
