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
    expect(within(missing).getAllByRole('listitem').map(item => item.querySelector('.dskills__name')?.textContent)).toEqual(['SQL', 'Docker'])
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
    await user.click(await screen.findByRole('button', { name: /^Save / }))

    expect(await screen.findByText('Couldn’t save “Junior Developer”.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Junior Developer' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(decide).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Junior Developer' })).not.toBeInTheDocument())
  })

  it('shows the null coverage copy and the empty state actions', async () => {
    const noRequirements = { ...JOB, match: { ...JOB.match, required_total: 0, required_matched: 0, coverage: null } }
    const client = makeClient({ list: vi.fn(async () => ({ items: [{ ...noRequirements }], has_more: false })) })
    renderFeed(client)
    expect(await screen.findByText('No skill requirements were extracted for this job.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /^Save / }))
    expect(await screen.findByText('You’ve seen everything that matches.')).toBeInTheDocument()
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
    await userEvent.click(screen.getAllByRole('button', { name: /^Save / })[0])
    expect(list).toHaveBeenCalledTimes(1)
    await act(async () => resolveDecision())
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2))
    expect(list).toHaveBeenLastCalledWith({}, 3, 20)
    // One card at a time: decide roles 2-4, then the prefetched role 5 is next.
    for (const title of ['Test role 2', 'Test role 3', 'Test role 4']) {
      await userEvent.click(await screen.findByRole('button', { name: `Save ${title}` }))
      await act(async () => resolveDecision())
    }
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
    await userEvent.click(screen.getByRole('button', { name: /^Save / }))
    expect(await screen.findByRole('heading', { name: 'Next job' })).toBeInTheDocument()
    expect(list).toHaveBeenLastCalledWith({}, 0, 20)
    await act(async () => resolveOldPage({ items: [next], has_more: false }))
    expect(screen.getAllByRole('heading', { name: 'Next job' })).toHaveLength(1)
    // Only one card renders, so also prove no duplicate is queued behind it.
    await userEvent.click(screen.getByRole('button', { name: 'Save Next job' }))
    expect(await screen.findByText('You’ve seen everything that matches.')).toBeInTheDocument()
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
    await userEvent.click(screen.getAllByRole('button', { name: /^Save / })[0])
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

  it('blocks filter changes while a decision is pending so a failed PUT stays visible', async () => {
    let rejectDecision!: (error: Error) => void
    const decision = new Promise<void>((_resolve, reject) => { rejectDecision = reject })
    const list = vi.fn<DiscoverClient['list']>(async () => ({ items: [JOB], has_more: false }))
    const user = userEvent.setup()
    renderFeed(makeClient({ list, decide: vi.fn(() => decision) }))

    await user.click(await screen.findByRole('button', { name: /^Save / }))
    expect(screen.getByRole('button', { name: 'Apply filters' })).toBeDisabled()
    expect(screen.queryByText('You’ve seen everything that matches.')).not.toBeInTheDocument()
    await user.type(screen.getByLabelText('Location'), 'Remote{Enter}')
    expect(list).toHaveBeenCalledTimes(1)
    expect(screen.getByLabelText('Current URL')).toHaveTextContent('')

    await act(async () => rejectDecision(new Error('offline')))
    expect(await screen.findByText('Couldn’t save “Junior Developer”.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Junior Developer' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Apply filters' })).toBeEnabled()
  })

  it('does not fail or show the empty state when the profile reload itself rejects', async () => {
    const reload = vi.fn(async () => { throw new Error('reload failed') })
    const client = makeClient({ list: vi.fn(async () => { throw { code: 'not_found', details: { resource: 'profile' } } }) })
    render(<MemoryRouter><DiscoverFeed client={client} onProfileMissing={reload} /></MemoryRouter>)
    expect(await screen.findByRole('heading', { name: 'Let’s set up your profile first.' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Go now' })).toHaveAttribute('href', '/welcome')
    expect(screen.queryByText('You’ve seen everything that matches.')).not.toBeInTheDocument()
  })

  it('rolls the card back when a decision fails even if the profile reload rejects', async () => {
    const reload = vi.fn(async () => { throw new Error('reload failed') })
    const decide = vi.fn(async () => { throw { status: 404, code: 'not_found', message: 'x', details: { resource: 'profile' } } })
    render(<MemoryRouter><DiscoverFeed client={makeClient({ decide })} onProfileMissing={reload} /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button', { name: /^Save / }))
    expect(await screen.findByText('Couldn’t save “Junior Developer”.')).toBeInTheDocument()
    expect(reload).toHaveBeenCalledTimes(1)
  })

  it('hides the empty state and disables Check again while decisions are pending', async () => {
    let resolveDecision!: () => void
    const decide = vi.fn(() => new Promise<void>(resolve => { resolveDecision = resolve }))
    renderFeed(makeClient({ decide }))
    await userEvent.click(await screen.findByRole('button', { name: /^Save / }))
    expect(screen.getByText('Saving your decision…')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Check again' })).not.toBeInTheDocument()
    await act(async () => resolveDecision())
    expect(await screen.findByRole('button', { name: 'Check again' })).toBeInTheDocument()
  })

  it('limits Location and Keyword to 100 characters and explains validation_failed', async () => {
    const list = vi.fn<DiscoverClient['list']>()
      .mockResolvedValueOnce({ items: [], has_more: false })
      .mockRejectedValueOnce({ status: 422, code: 'validation_failed', message: 'bad', details: { field: 'q' } })
    const user = userEvent.setup()
    renderFeed(makeClient({ list }))
    expect(screen.getByLabelText('Location')).toHaveAttribute('maxlength', '100')
    expect(screen.getByLabelText('Keyword')).toHaveAttribute('maxlength', '100')
    await user.type(screen.getByLabelText('Keyword'), 'x')
    await user.click(screen.getByRole('button', { name: 'Apply filters' }))
    expect(await screen.findByText(/Those filters are not valid/)).toBeInTheDocument()
  })

  it('drops a card whose job is no longer available instead of offering a retry', async () => {
    const decide = vi.fn(async () => { throw { status: 404, code: 'not_found', message: 'gone', details: { resource: 'job' } } })
    renderFeed(makeClient({ decide }))
    await userEvent.click(await screen.findByRole('button', { name: /^Save / }))
    expect(await screen.findByText('This job is no longer available.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Junior Developer' })).not.toBeInTheDocument()
  })

  it('moves focus to the next card and gives buttons job context', async () => {
    const second = { ...JOB, job: { ...JOB.job, job_id: '00000000-0000-4000-8000-000000000002', title: 'Second role' } }
    const client = makeClient({ list: vi.fn(async () => ({ items: [JOB, second], has_more: false })) })
    renderFeed(client)
    const save = await screen.findByRole('button', { name: 'Save Junior Developer' })
    expect(save).toHaveAttribute('aria-keyshortcuts', 'ArrowRight')
    expect(screen.getByRole('button', { name: 'Not interested in Junior Developer' })).toHaveAttribute('aria-keyshortcuts', 'ArrowLeft')
    expect(screen.queryByRole('button', { name: 'Save Second role' })).not.toBeInTheDocument()
    await userEvent.click(save)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save Second role' })).toHaveFocus())
    expect(screen.getByRole('button', { name: 'Save Second role' })).toHaveAttribute('aria-keyshortcuts', 'ArrowRight')
  })

  it('renders Open posting only for http(s) application URLs', async () => {
    const unsafe = { ...JOB, job: { ...JOB.job, application_url: 'javascript:alert(1)' } }
    renderFeed(makeClient({ list: vi.fn(async () => ({ items: [unsafe], has_more: false })) }))
    await screen.findByRole('heading', { name: 'Junior Developer' })
    expect(screen.queryByRole('link', { name: 'Open posting' })).not.toBeInTheDocument()
  })

  it('Change filters focuses the filter controls and Check again reloads the feed', async () => {
    const list = vi.fn(async (): Promise<DiscoverResponse> => ({ items: [], has_more: false }))
    const user = userEvent.setup()
    renderFeed(makeClient({ list }))
    await user.click(await screen.findByRole('button', { name: 'Change filters' }))
    expect(screen.getByLabelText('Job type')).toHaveFocus()
    expect(list).toHaveBeenCalledTimes(1)
    await user.click(screen.getByRole('button', { name: 'Check again' }))
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2))
  })

  it('refreshes profile state when Discover reports a missing profile', async () => {
    const client = makeClient({ list: vi.fn(async () => { throw { code: 'not_found', details: { resource: 'profile' } } }) })
    const reload = vi.fn()
    render(<MemoryRouter><DiscoverFeed client={client} onProfileMissing={reload} /></MemoryRouter>)
    await waitFor(() => expect(reload).toHaveBeenCalledTimes(1))
  })

  it('opens the mobile filter sheet as a modal dialog, locks page scroll, and Escape closes it back to Filters', async () => {
    const user = userEvent.setup()
    renderFeed(makeClient())
    const filters = await screen.findByRole('button', { name: 'Filters' })
    expect(filters).toHaveAttribute('aria-expanded', 'false')

    await user.click(filters)
    const sheet = screen.getByRole('dialog', { name: 'Filters' })
    expect(sheet).toHaveAttribute('aria-modal', 'true')
    expect(filters).toHaveAttribute('aria-expanded', 'true')
    expect(document.body.style.overflow).toBe('hidden')
    expect(sheet).toContainElement(document.activeElement as HTMLElement)

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog', { name: 'Filters' })).not.toBeInTheDocument()
    expect(document.body.style.overflow).toBe('')
    expect(filters).toHaveFocus()
  })
})
