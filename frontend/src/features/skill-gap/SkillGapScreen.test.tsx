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
    expect(MOCK_ROLES.items.every(item => item.job_count > 0)).toBe(true)
    expect(screen.getByText('✓ You have this')).toBeInTheDocument()
    expect(screen.getByText('REQUIRED 7 · PREFERRED 2')).toBeInTheDocument()
    expect(screen.getByText('Experience mentioned: up to 3 yrs (4 postings)')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Python: 75% of postings' })).toBeInTheDocument()
    expect(screen.getByText('You have 1 of the top 3 skills for this role.')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Target role'), { target: { value: 'Data Science' } })
    expect(await screen.findByText(/Based on 4 active postings/)).toBeInTheDocument()
    expect(screen.getByText(/Small sample/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Target role'), { target: { value: 'Unclassified' } })
    expect(await screen.findByText('Based on 2 active postings for Unclassified')).toBeInTheDocument()
  })

  it('does not warn at the five-posting boundary', async () => {
    const atBoundary: SkillGapResponse = { role_category: 'Boundary', sample_size: 5, skills: [], summary: { top_n: 0, user_has_in_top_n: 0 } }
    const roles = { items: [{ role_category: 'Boundary', job_count: 5 }] }
    render(<SkillGapScreen client={createMockSkillGapClient({ roles, gapByRole: { Boundary: atBoundary } })} />)
    expect(await screen.findByText('Based on 5 active postings for Boundary')).toBeInTheDocument()
    expect(screen.queryByText(/Small sample/)).not.toBeInTheDocument()
  })

  it('renders a zero-sample skill as 0% without invalid values and hides summary for an empty result', async () => {
    const zeroSample: SkillGapResponse = { role_category: 'Unclassified', sample_size: 0, skills: [{ skill_id: 50, name: 'Zero sample skill', job_count: 0, frequency: 0, required_count: 0, preferred_count: 0, max_minimum_years: null, years_mentions: 0, user_has: false }], summary: { top_n: 1, user_has_in_top_n: 0 } }
    const emptyResult: SkillGapResponse = { role_category: 'Empty result', sample_size: 0, skills: [], summary: { top_n: 0, user_has_in_top_n: 0 } }
    const client = createMockSkillGapClient({
      roles: { items: [{ role_category: 'Unclassified', job_count: 1 }, { role_category: 'Empty result', job_count: 1 }] },
      gapByRole: { Unclassified: zeroSample, 'Empty result': emptyResult },
    })
    const { container } = render(<SkillGapScreen client={client} />)
    expect(await screen.findByText('Based on 0 active postings for Unclassified')).toBeInTheDocument()
    expect(screen.getByText('0 / 0 postings · 0%')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Zero sample skill: 0% of postings' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Zero sample skill: 0% of postings' }).firstElementChild).toHaveStyle({ width: '0%' })
    expect(container.textContent).not.toMatch(/NaN|Infinity/)
    fireEvent.change(screen.getByLabelText('Target role'), { target: { value: 'Empty result' } })
    expect(await screen.findByText('No skill requirements are available for this role yet.')).toBeInTheDocument()
    expect(container.querySelector('.skill-gap__summary')).not.toBeInTheDocument()
    cleanup()
    render(<SkillGapScreen client={createMockSkillGapClient({ roles: { items: [] } })} />)
    expect(await screen.findByText('No roles have active postings yet.')).toBeInTheDocument()
    expect(screen.queryByLabelText('Target role')).not.toBeInTheDocument()
  })

  it('uses the API top_n in the summary for three and ten skills, and hides it for zero', async () => {
    const skills = (n: number) => Array.from({ length: n }, (_, index) => ({ skill_id: 100 + index, name: `Skill ${index + 1}`, job_count: n - index, frequency: 1, required_count: n - index, preferred_count: 0, max_minimum_years: null, years_mentions: 0, user_has: index === 0 }))
    const short: SkillGapResponse = { role_category: 'Short', sample_size: 3, skills: skills(3), summary: { top_n: 3, user_has_in_top_n: 1 } }
    const full: SkillGapResponse = { role_category: 'Full', sample_size: 10, skills: skills(10), summary: { top_n: 10, user_has_in_top_n: 1 } }
    const empty: SkillGapResponse = { role_category: 'Empty', sample_size: 0, skills: [], summary: { top_n: 0, user_has_in_top_n: 0 } }
    const client = createMockSkillGapClient({ roles: { items: [{ role_category: 'Short', job_count: 3 }, { role_category: 'Full', job_count: 10 }, { role_category: 'Empty', job_count: 1 }] }, gapByRole: { Short: short, Full: full, Empty: empty } })
    const { container } = render(<SkillGapScreen client={client} />)
    expect(await screen.findByText('You have 1 of the top 3 skills for this role.')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Target role'), { target: { value: 'Full' } })
    expect(await screen.findByText('You have 1 of the top 10 skills for this role.')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Target role'), { target: { value: 'Empty' } })
    await screen.findByText('No skill requirements are available for this role yet.')
    expect(container.querySelector('.skill-gap__summary')).not.toBeInTheDocument()
  })

  it('only renders the role label when its select is available', async () => {
    let resolveRoles!: (value: { items: { role_category: string; job_count: number }[] }) => void
    const client: SkillGapClient = { roles: () => new Promise(resolve => { resolveRoles = resolve }), forRole: async role => ({ role_category: role, sample_size: 0, skills: [], summary: { top_n: 0, user_has_in_top_n: 0 } }), add: async () => undefined }
    const { container } = render(<SkillGapScreen client={client} />)
    expect(screen.queryByLabelText('Target role')).not.toBeInTheDocument()
    resolveRoles({ items: [{ role_category: 'Available', job_count: 1 }] })
    expect(await screen.findByLabelText('Target role')).toBeInTheDocument()
    expect(container.querySelector('main section[aria-live]')).not.toBeInTheDocument()
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
    expect(screen.getByText('You have 2 of the top 3 skills for this role.')).toBeInTheDocument()
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

  it('keeps a successfully added skill confirmed when the selected role also contains it', async () => {
    let finishAdd!: () => void
    const shared = { skill_id: 42, name: 'TypeScript', job_count: 4, frequency: .8, required_count: 3, preferred_count: 1, max_minimum_years: null, years_mentions: 0, user_has: false }
    const client: SkillGapClient = {
      roles: async () => ({ items: [{ role_category: 'Role A', job_count: 5 }, { role_category: 'Role B', job_count: 5 }] }),
      forRole: async role => ({ role_category: role, sample_size: 5, skills: [{ ...shared }], summary: { top_n: 1, user_has_in_top_n: 0 } }),
      add: vi.fn(() => new Promise<void>(resolve => { finishAdd = resolve })),
    }
    render(<SkillGapScreen client={client} />)
    await screen.findByText('Based on 5 active postings for Role A')
    const rowA = screen.getByText('TypeScript').closest('li')!
    fireEvent.click(within(rowA).getByLabelText('I already have this skill'))
    fireEvent.click(within(rowA).getByRole('button', { name: 'Add to my skills' }))
    fireEvent.change(screen.getByLabelText('Target role'), { target: { value: 'Role B' } })
    expect(await screen.findByText('Based on 5 active postings for Role B')).toBeInTheDocument()
    expect(screen.getByText('You have 0 of the top 1 skills for this role.')).toBeInTheDocument()
    finishAdd()
    expect(await screen.findByText('✓ You have this')).toBeInTheDocument()
    expect(screen.getByText('You have 1 of the top 1 skills for this role.')).toBeInTheDocument()
    expect(screen.getByText('Based on 5 active postings for Role B')).toBeInTheDocument()
  })

  it('overlays a successful add on a role GET that resolves afterward', async () => {
    let resolveRoleB!: (value: SkillGapResponse) => void
    let finishAdd!: () => void
    const shared = { skill_id: 43, name: 'Go', job_count: 4, frequency: .8, required_count: 3, preferred_count: 1, max_minimum_years: null, years_mentions: 0, user_has: false }
    const client: SkillGapClient = {
      roles: async () => ({ items: [{ role_category: 'Role A', job_count: 5 }, { role_category: 'Role B', job_count: 5 }] }),
      forRole: vi.fn((role: string) => role === 'Role A'
        ? Promise.resolve({ role_category: role, sample_size: 5, skills: [{ ...shared }], summary: { top_n: 1, user_has_in_top_n: 0 } })
        : new Promise<SkillGapResponse>(resolve => { resolveRoleB = resolve })),
      add: vi.fn(() => new Promise<void>(resolve => { finishAdd = resolve })),
    }
    render(<SkillGapScreen client={client} />)
    await screen.findByText('Based on 5 active postings for Role A')
    const rowA = screen.getByText('Go').closest('li')!
    fireEvent.click(within(rowA).getByLabelText('I already have this skill'))
    fireEvent.click(within(rowA).getByRole('button', { name: 'Add to my skills' }))
    fireEvent.change(screen.getByLabelText('Target role'), { target: { value: 'Role B' } })
    await waitFor(() => expect(client.forRole).toHaveBeenCalledTimes(2))
    finishAdd()
    resolveRoleB({ role_category: 'Role B', sample_size: 5, skills: [{ ...shared }], summary: { top_n: 1, user_has_in_top_n: 0 } })
    expect(await screen.findByText('✓ You have this')).toBeInTheDocument()
    expect(screen.getByText('You have 1 of the top 1 skills for this role.')).toBeInTheDocument()
  })

  it('routes a coded missing-profile response to onboarding using details.resource', async () => {
    const client = createMockSkillGapClient({ gapError: { status: 404, code: 'not_found', message: 'Profile missing', details: { resource: 'profile' } } })
    render(<MemoryRouter><SkillGapScreen client={client} /></MemoryRouter>)
    await screen.findByText('Profile missing')
    expect(screen.getByRole('link', { name: 'Start onboarding' })).toHaveAttribute('href', '/welcome')
  })

  it('retries role and gap errors and renders recovered data', async () => {
    const base = createMockSkillGapClient()
    let roleAttempts = 0
    const roleClient: SkillGapClient = { ...base, roles: vi.fn(async () => { if (++roleAttempts === 1) throw { status: 503, code: 'service_unavailable', message: 'Roles unavailable' }; return { items: [{ role_category: 'Recovered role', job_count: 6 }] } }), forRole: async role => ({ role_category: role, sample_size: 6, skills: [], summary: { top_n: 0, user_has_in_top_n: 0 } }) }
    render(<SkillGapScreen client={roleClient} />)
    expect(await screen.findByText('Roles unavailable')).toBeInTheDocument()
    expect(screen.queryByLabelText('Target role')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry roles' }))
    expect(await screen.findByText('Based on 6 active postings for Recovered role')).toBeInTheDocument()
    expect(roleAttempts).toBe(2)
    cleanup()

    let gapAttempts = 0
    const gapResponse: SkillGapResponse = { role_category: 'Retry role', sample_size: 6, skills: [{ skill_id: 88, name: 'Rust', job_count: 3, frequency: .5, required_count: 2, preferred_count: 1, max_minimum_years: null, years_mentions: 0, user_has: false }], summary: { top_n: 1, user_has_in_top_n: 0 } }
    const gapClient: SkillGapClient = { roles: async () => ({ items: [{ role_category: 'Retry role', job_count: 6 }] }), forRole: vi.fn(async () => { if (++gapAttempts === 1) throw { status: 503, code: 'service_unavailable', message: 'Gaps unavailable' }; return gapResponse }), add: async () => undefined }
    render(<SkillGapScreen client={gapClient} />)
    expect(await screen.findByText('Gaps unavailable')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry skill gaps' }))
    expect(await screen.findByText('Based on 6 active postings for Retry role')).toBeInTheDocument()
    expect(screen.getByText('Rust')).toBeInTheDocument()
    expect(gapAttempts).toBe(2)
  })
})
