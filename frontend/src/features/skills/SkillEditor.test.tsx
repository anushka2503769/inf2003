import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { UserSkill } from '../../types/api'
import type { SkillsClient, SkillsClientError } from './client'
import { SkillEditor } from './SkillEditor'
import type { SkillSearchResponse } from './types'

/**
 * A hand-built fake, not `createMockSkillsClient` from client.ts. The point
 * of this suite is to prove `SkillEditor` behaves correctly against
 * *anything* implementing `SkillsClient` — including the real adapter
 * ANU-02 will introduce — not to prove today's mock fixtures are
 * self-consistent (that belongs in mocks.test.ts, separately).
 */
function makeFakeClient(overrides: Partial<SkillsClient> = {}): SkillsClient {
  return {
    search: vi.fn(async (): Promise<SkillSearchResponse> => ({ items: [], has_more: false })),
    add: vi.fn(async () => undefined),
    remove: vi.fn(async () => undefined),
    ...overrides,
  }
}

function clientError(status: number, code: string, message: string): SkillsClientError {
  return { status, code, message }
}

const PYTHON = { skill_id: 1, name: 'Python' }
const SQL = { skill_id: 2, name: 'SQL' }
const RUST = { skill_id: 3, name: 'Rust' }

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
})

afterEach(() => {
  // This suite runs with vitest's `globals: false` (matching the rest of the
  // repo's explicit-import style), so Testing Library's own auto-cleanup —
  // which only registers against a *global* afterEach — never fires. Without
  // this, unmounted trees from earlier tests stay in the DOM and later
  // `getByText` queries can match stale nodes from a previous test.
  cleanup()
  vi.useRealTimers()
})

describe('initial render and search', () => {
  it('loads the empty-query list on mount without waiting for the debounce', async () => {
    const client = makeFakeClient({
      search: vi.fn(async () => ({ items: [PYTHON, SQL], has_more: false })),
    })

    render(<SkillEditor confirmedSkills={[]} onProfileReload={vi.fn()} client={client} />)

    await waitFor(() => expect(screen.getByText('Python')).toBeInTheDocument())
    expect(client.search).toHaveBeenCalledWith('', 20)
    expect(client.search).toHaveBeenCalledTimes(1) // no duplicate call from the debounce effect
  })

  it('shows the empty-results state distinctly from "no skills in the dictionary"', async () => {
    const client = makeFakeClient({
      search: vi.fn(async () => ({ items: [], has_more: false })),
    })
    render(<SkillEditor confirmedSkills={[]} onProfileReload={vi.fn()} client={client} />)

    await waitFor(() => expect(screen.getByText(/no skills are in the dictionary/i)).toBeInTheDocument())
  })

  it('asks the student to narrow their query when has_more is true, without paginating', async () => {
    const client = makeFakeClient({
      search: vi.fn(async () => ({ items: [PYTHON], has_more: true })),
    })
    render(<SkillEditor confirmedSkills={[]} onProfileReload={vi.fn()} client={client} />)

    await waitFor(() => expect(screen.getByText(/narrow your search/i)).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /next|more results|page/i })).not.toBeInTheDocument()
  })

  it('debounces keystrokes into a single search after the user stops typing', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    const client = makeFakeClient({
      search: vi.fn(async () => ({ items: [PYTHON], has_more: false })),
    })
    render(<SkillEditor confirmedSkills={[]} onProfileReload={vi.fn()} client={client} />)
    await waitFor(() => expect(client.search).toHaveBeenCalledTimes(1)) // initial mount search

    await user.type(screen.getByLabelText(/search the skill dictionary/i), 'Py')

    // Debounce window hasn't elapsed yet: still just the initial call.
    expect(client.search).toHaveBeenCalledTimes(1)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(350)
    })

    expect(client.search).toHaveBeenCalledTimes(2)
    expect(client.search).toHaveBeenLastCalledWith('Py', 20)
  })

  it('ignores a stale search response that resolves after a newer one', async () => {
    let resolveFirst!: (value: SkillSearchResponse) => void
    const firstCall = new Promise<SkillSearchResponse>(resolve => {
      resolveFirst = resolve
    })

    const search = vi
      .fn<SkillsClient['search']>()
      .mockImplementationOnce(() => firstCall) // the initial mount search, deliberately held open
      .mockImplementationOnce(async () => ({ items: [RUST], has_more: false })) // the debounced search

    const client = makeFakeClient({ search })
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    render(<SkillEditor confirmedSkills={[]} onProfileReload={vi.fn()} client={client} />)

    await user.type(screen.getByLabelText(/search the skill dictionary/i), 'Rust')
    await act(async () => {
      await vi.advanceTimersByTimeAsync(350)
    })
    await waitFor(() => expect(screen.getByText('Rust')).toBeInTheDocument())

    // Now the slow initial request finally resolves. If it were applied, it
    // would stomp the newer "Rust" result with a stale "Python" result.
    await act(async () => {
      resolveFirst({ items: [PYTHON], has_more: false })
    })

    expect(screen.getByText('Rust')).toBeInTheDocument()
    expect(screen.queryByText('Python')).not.toBeInTheDocument()
  })

  it('surfaces a search failure without crashing and without showing stale results as current', async () => {
    const client = makeFakeClient({
      search: vi.fn(async () => {
        throw clientError(503, 'SERVICE_UNAVAILABLE', 'The server had a problem with that request.')
      }),
    })
    render(<SkillEditor confirmedSkills={[]} onProfileReload={vi.fn()} client={client} />)

    await waitFor(() =>
      expect(screen.getByText('The server had a problem with that request.')).toBeInTheDocument(),
    )
  })
})

describe('adding a skill', () => {
  it('adds a skill and only clears pending state after the profile reload resolves', async () => {
    const client = makeFakeClient({
      search: vi.fn(async () => ({ items: [PYTHON], has_more: false })),
      add: vi.fn(async () => undefined),
    })
    let resolveReload!: () => void
    const onProfileReload = vi.fn(
      () =>
        new Promise<void>(resolve => {
          resolveReload = resolve
        }),
    )

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    render(<SkillEditor confirmedSkills={[]} onProfileReload={onProfileReload} client={client} />)
    await waitFor(() => expect(screen.getByText('Python')).toBeInTheDocument())

    const row = screen.getByText('Python').closest('li')!
    await user.click(within(row).getByRole('button', { name: /^add$/i }))

    expect(client.add).toHaveBeenCalledWith(1)
    expect(within(row).getByRole('button', { name: /adding/i })).toBeDisabled()
    expect(onProfileReload).toHaveBeenCalledTimes(1)

    await act(async () => resolveReload())

    // Once the shell's reload resolves, the row returns to its normal label;
    // SkillEditor never claims success before the reload actually lands.
    await waitFor(() => expect(within(row).getByRole('button', { name: /^add$/i })).toBeEnabled())
  })

  it('shows SKILL_NOT_FOUND inline and never calls onProfileReload for a failed add', async () => {
    const client = makeFakeClient({
      search: vi.fn(async () => ({ items: [PYTHON], has_more: false })),
      add: vi.fn(async () => {
        throw clientError(404, 'SKILL_NOT_FOUND', 'That skill is no longer available.')
      }),
    })
    const onProfileReload = vi.fn(async () => undefined)

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    render(<SkillEditor confirmedSkills={[]} onProfileReload={onProfileReload} client={client} />)
    await waitFor(() => expect(screen.getByText('Python')).toBeInTheDocument())

    const row = screen.getByText('Python').closest('li')!
    await user.click(within(row).getByRole('button', { name: /^add$/i }))

    await waitFor(() =>
      expect(within(row).getByText('That skill is no longer available.')).toBeInTheDocument(),
    )
    expect(onProfileReload).not.toHaveBeenCalled()
    // The row must not silently claim success: the Add button is back, not "Added".
    expect(within(row).getByRole('button', { name: /^add$/i })).toBeEnabled()
  })

  it('reports a reload failure as "saved, but" — never as the add itself failing', async () => {
    const client = makeFakeClient({
      search: vi.fn(async () => ({ items: [PYTHON], has_more: false })),
      add: vi.fn(async () => undefined),
    })
    const onProfileReload = vi.fn(async () => {
      throw new Error('network down')
    })

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    render(<SkillEditor confirmedSkills={[]} onProfileReload={onProfileReload} client={client} />)
    await waitFor(() => expect(screen.getByText('Python')).toBeInTheDocument())

    const row = screen.getByText('Python').closest('li')!
    await user.click(within(row).getByRole('button', { name: /^add$/i }))

    await waitFor(() => expect(within(row).getByText(/saved, but/i)).toBeInTheDocument())
  })

  it('serializes rapid double-clicks on the same skill into a single add call', async () => {
    let resolveAdd!: () => void
    const client = makeFakeClient({
      search: vi.fn(async () => ({ items: [PYTHON], has_more: false })),
      add: vi.fn(
        () =>
          new Promise<void>(resolve => {
            resolveAdd = resolve
          }),
      ),
    })
    const onProfileReload = vi.fn(async () => undefined)

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    render(<SkillEditor confirmedSkills={[]} onProfileReload={onProfileReload} client={client} />)
    await waitFor(() => expect(screen.getByText('Python')).toBeInTheDocument())

    const row = screen.getByText('Python').closest('li')!
    const button = within(row).getByRole('button', { name: /^add$/i })
    await user.click(button)
    // Fire a second click while the first is still in flight. The button is
    // disabled by then, but the assertion below is what actually matters.
    await user.click(button)

    expect(client.add).toHaveBeenCalledTimes(1)
    await act(async () => resolveAdd())
  })
})

describe('removing a skill', () => {
  const confirmed: UserSkill[] = [PYTHON, SQL]

  it('removes a confirmed skill and reloads on success', async () => {
    const client = makeFakeClient({ remove: vi.fn(async () => undefined) })
    const onProfileReload = vi.fn(async () => undefined)

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    render(<SkillEditor confirmedSkills={confirmed} onProfileReload={onProfileReload} client={client} />)

    const row = screen.getByText('SQL').closest('li')!
    await user.click(within(row).getByRole('button', { name: /^remove$/i }))

    expect(client.remove).toHaveBeenCalledWith(2)
    await waitFor(() => expect(onProfileReload).toHaveBeenCalledTimes(1))
  })

  it('a repeated remove of an already-absent link is treated as success (idempotent no-op)', async () => {
    // Per contract, DELETE on an absent link still returns 204 — the fake
    // simply always resolves, proving SkillEditor doesn't require a prior
    // "exists" check before allowing the click.
    const client = makeFakeClient({ remove: vi.fn(async () => undefined) })
    const onProfileReload = vi.fn(async () => undefined)

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    render(<SkillEditor confirmedSkills={confirmed} onProfileReload={onProfileReload} client={client} />)

    const row = screen.getByText('Python').closest('li')!
    await user.click(within(row).getByRole('button', { name: /^remove$/i }))
    await waitFor(() => expect(onProfileReload).toHaveBeenCalledTimes(1))
    expect(client.remove).toHaveBeenCalledWith(1)
  })
})

describe('search results already confirmed', () => {
  it('shows "Added" instead of an Add button for a skill already confirmed', async () => {
    const client = makeFakeClient({
      search: vi.fn(async () => ({ items: [PYTHON, RUST], has_more: false })),
    })

    render(
      <SkillEditor confirmedSkills={[PYTHON]} onProfileReload={vi.fn()} client={client} />,
    )

    await waitFor(() => expect(screen.getAllByText('Python')).not.toHaveLength(0))
    const pythonResultRow = screen.getAllByText('Python').at(-1)!.closest('li')!
    expect(within(pythonResultRow).getByText('Added')).toBeInTheDocument()
    expect(within(pythonResultRow).queryByRole('button', { name: /^add$/i })).not.toBeInTheDocument()

    const rustRow = screen.getByText('Rust').closest('li')!
    expect(within(rustRow).getByRole('button', { name: /^add$/i })).toBeInTheDocument()
  })
})