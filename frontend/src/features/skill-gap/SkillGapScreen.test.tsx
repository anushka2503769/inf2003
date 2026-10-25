import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

import { SkillGapScreen } from '../../screens/SkillGapScreen'
import { createMockSkillGapClient, MOCK_ROLES } from './mocks'
import type { SkillGapClient, SkillGapResponse } from './types'

afterEach(cleanup)

describe('SkillGapScreen', () => {
  it('shows roles with counts, ranked details, bar, experience and sample warning below five', async () => {
    render(<SkillGapScreen client={createMockSkillGapClient()} />)
    expect(await screen.findByText('Based on 12 active postings for Software Engineering')).toBeInTheDocument()
    expect(screen.getByLabelText('Target role')).toHaveTextContent('Software Engineering (12)')
    expect(screen.getByText('✓ You have this')).toBeInTheDocument()
    expect(screen.getByText('REQUIRED 7 · PREFERRED 2')).toBeInTheDocument()
    expect(screen.getByText('Experience mentioned: up to 3 yrs (4 postings)')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Python: 75% of postings' })).toBeInTheDocument()
    expect(screen.getByText('You have 1 of the top 10 skills for this role.')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Target role'), { target: { value: 'Data Science' } })
    expect(await screen.findByText(/Based on 4 active postings/)).toBeInTheDocument()
    expect(screen.getByText(/Small sample/)).toBeInTheDocument()
  })

  it('does not warn at the five-posting boundary', async () => {
    const atBoundary: SkillGapResponse = { role_category: 'Boundary', sample_size: 5, skills: [], summary: { top_n: 0, user_has_in_top_n: 0 } }
    const roles = { items: [{ role_category: 'Boundary', job_count: 5 }] }
    render(<SkillGapScreen client={createMockSkillGapClient({ roles, gapByRole: { Boundary: atBoundary } })} />)
    expect(await screen.findByText('Based on 5 active postings for Boundary')).toBeInTheDocument()
    expect(screen.queryByText(/Small sample/)).not.toBeInTheDocument()
  })

  it('shows zero sample without invalid percentages and supports empty roles', async () => {
    render(<SkillGapScreen client={createMockSkillGapClient()} />)
    await screen.findByText(/Based on 12 active postings/)
    fireEvent.change(screen.getByLabelText('Target role'), { target: { value: 'Unclassified' } })
    expect(await screen.findByText('Based on 0 active postings for Unclassified')).toBeInTheDocument()
    expect(screen.getByText('No skill requirements are available for this role yet.')).toBeInTheDocument()
    cleanup()
    render(<SkillGapScreen client={createMockSkillGapClient({ roles: { items: [] } })} />)
    expect(await screen.findByText('No roles have active postings yet.')).toBeInTheDocument()
  })

  it('requires explicit confirmation, updates the has state and summary on successful add', async () => {
    const client = createMockSkillGapClient()
    render(<SkillGapScreen client={client} />)
    await screen.findByText(/Based on 12 active postings/)
    const row = screen.getByText('React').closest('li')!
    const checkbox = within(row).getByLabelText('I already have this skill')
    const add = within(row).getByRole('button', { name: 'Add to my skills' })
    expect(add).toBeDisabled()
    fireEvent.click(checkbox)
    expect(add).toBeEnabled()
    fireEvent.click(add)
    expect(await within(row).findByText('✓ You have this')).toBeInTheDocument()
    expect(screen.getByText('You have 2 of the top 10 skills for this role.')).toBeInTheDocument()
  })

  it('retains the gap and offers retry after add failure', async () => {
    const client = createMockSkillGapClient({ addError: { status: 503, code: 'service_unavailable', message: 'Temporary outage' } })
    render(<SkillGapScreen client={client} />)
    await screen.findByText(/Based on 12 active postings/)
    const row = screen.getByText('React').closest('li')!
    fireEvent.click(within(row).getByLabelText('I already have this skill'))
    fireEvent.click(within(row).getByRole('button', { name: 'Add to my skills' }))
    expect(await within(row).findByText(/Temporary outage/)).toBeInTheDocument()
    expect(within(row).getByText('Gap')).toBeInTheDocument()
    expect(within(row).getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })

  it('ignores a late result from the previously selected role', async () => {
    let resolveOld!: (value: SkillGapResponse) => void
    const client: SkillGapClient = {
      roles: async () => MOCK_ROLES,
      forRole: vi.fn((role: string) => role === 'Software Engineering' ? new Promise<SkillGapResponse>(resolve => { resolveOld = resolve }) : Promise.resolve({ role_category: role, sample_size: 5, skills: [], summary: { top_n: 0, user_has_in_top_n: 0 } })),
      add: vi.fn(async () => undefined),
    }
    render(<SkillGapScreen client={client} />)
    fireEvent.change(await screen.findByLabelText('Target role'), { target: { value: 'Data Science' } })
    expect(await screen.findByText('Based on 5 active postings for Data Science')).toBeInTheDocument()
    resolveOld({ role_category: 'Software Engineering', sample_size: 99, skills: [], summary: { top_n: 0, user_has_in_top_n: 0 } })
    await waitFor(() => expect(screen.queryByText(/Based on 99/)).not.toBeInTheDocument())
  })

  it('unlocks the newly selected role while an old-role add is still pending', async () => {
    let finishAdd!: () => void
    const base = createMockSkillGapClient()
    const client: SkillGapClient = { ...base, add: vi.fn(() => new Promise<void>(resolve => { finishAdd = resolve })) }
    render(<SkillGapScreen client={client} />)
    await screen.findByText(/Based on 12 active postings/)
    const reactRow = screen.getByText('React').closest('li')!
    fireEvent.click(within(reactRow).getByLabelText('I already have this skill'))
    fireEvent.click(within(reactRow).getByRole('button', { name: 'Add to my skills' }))
    fireEvent.change(screen.getByLabelText('Target role'), { target: { value: 'Data Science' } })
    expect(await screen.findByText('Based on 4 active postings for Data Science')).toBeInTheDocument()
    const statisticsRow = screen.getByText('Statistics').closest('li')!
    fireEvent.click(within(statisticsRow).getByLabelText('I already have this skill'))
    expect(within(statisticsRow).getByRole('button', { name: 'Add to my skills' })).toBeEnabled()
    finishAdd()
  })

  it('routes a coded missing-profile response to onboarding using details.resource', async () => {
    const client = createMockSkillGapClient({ gapError: { status: 404, code: 'not_found', message: 'Profile missing', details: { resource: 'profile' } } })
    render(<MemoryRouter><SkillGapScreen client={client} /></MemoryRouter>)
    await screen.findByText('Profile missing')
    expect(screen.getByRole('link', { name: 'Start onboarding' })).toHaveAttribute('href', '/welcome')
  })

  it('renders role and gap loading errors with retry controls', async () => {
    const roleClient = createMockSkillGapClient({ roleError: { status: 503, code: 'service_unavailable', message: 'Roles unavailable' } })
    render(<SkillGapScreen client={roleClient} />)
    expect(await screen.findByText(/Roles unavailable/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry roles' })).toBeInTheDocument()
    cleanup()
    const gapClient = createMockSkillGapClient({ gapError: { status: 503, code: 'service_unavailable', message: 'Gaps unavailable' } })
    render(<SkillGapScreen client={gapClient} />)
    expect(await screen.findByText(/Gaps unavailable/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry skill gaps' })).toBeInTheDocument()
  })
})
