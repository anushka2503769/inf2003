import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { SkillsClient } from '../skills/client'
import type { ResumeClient } from './client'
import { ResumeSection } from './ResumeSection'
import type { ResumeResponse } from './types'
import { RESUME_MAX_BYTES } from './validation'

afterEach(cleanup)

const PYTHON = { skill_id: 1, name: 'Python' }
const SQL = { skill_id: 2, name: 'SQL' }
const GIT = { skill_id: 3, name: 'Git' }

function resume(overrides: Partial<ResumeResponse> = {}): ResumeResponse {
  return {
    resume_id: 'r1',
    user_id: 'u1',
    file_name: 'synthetic-cv.pdf',
    uploaded_at: '2026-10-20T08:30:00Z',
    extracted_data: { skills: ['Python', 'SQL', 'Git'], education: [], experience: [], projects: [] },
    suggested_skills: [GIT, PYTHON, SQL],
    ...overrides,
  }
}

function resumeClient(overrides: Partial<ResumeClient> = {}): ResumeClient {
  return {
    current: vi.fn(async () => null),
    upload: vi.fn(async () => resume()),
    ...overrides,
  }
}

function skillsClient(overrides: Partial<SkillsClient> = {}): SkillsClient {
  return {
    search: vi.fn(async () => ({ items: [], has_more: false })),
    add: vi.fn(async () => undefined),
    remove: vi.fn(async () => undefined),
    ...overrides,
  }
}

function pickFile(file: File) {
  fireEvent.change(screen.getByLabelText('Resume file'), { target: { files: [file] } })
}

const pdf = () => new File(['synthetic'], 'cv.pdf', { type: 'application/pdf' })

function mount(client: ResumeClient, skills: SkillsClient, reload = vi.fn(async () => undefined)) {
  render(<ResumeSection confirmedSkills={[]} onProfileReload={reload} client={client} skillsClient={skills} />)
  return reload
}

describe('current resume', () => {
  it('says "No resume yet" when the server has none', async () => {
    mount(resumeClient(), skillsClient())
    expect(await screen.findByText(/No resume yet/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Upload resume' })).toBeEnabled()
  })

  it('shows the file name and upload time of the current resume', async () => {
    mount(resumeClient({ current: vi.fn(async () => resume()) }), skillsClient())
    expect(await screen.findByText('synthetic-cv.pdf')).toBeInTheDocument()
    expect(screen.getByText(/Uploaded 20 Oct 2026/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Replace resume' })).toBeInTheDocument()
  })
})

describe('upload validation', () => {
  it('rejects a file of the wrong type without calling the server', async () => {
    const client = resumeClient()
    mount(client, skillsClient())
    await screen.findByText(/No resume yet/)
    pickFile(new File(['x'], 'notes.txt', { type: 'text/plain' }))
    expect(await screen.findByText(/Choose a PDF or DOCX file/)).toBeInTheDocument()
    expect(client.upload).not.toHaveBeenCalled()
  })

  it('rejects a file over 5 MB without calling the server', async () => {
    const client = resumeClient()
    mount(client, skillsClient())
    await screen.findByText(/No resume yet/)
    const big = new File(['x'], 'big.pdf', { type: 'application/pdf' })
    Object.defineProperty(big, 'size', { value: RESUME_MAX_BYTES + 1 })
    pickFile(big)
    expect(await screen.findByText(/The limit is 5 MB/)).toBeInTheDocument()
    expect(client.upload).not.toHaveBeenCalled()
  })

  it('shows the server message when the upload fails', async () => {
    const client = resumeClient({
      upload: vi.fn(async () => {
        throw { status: 404, code: 'not_found', message: 'Complete your profile before uploading a resume.' }
      }),
    })
    mount(client, skillsClient())
    await screen.findByText(/No resume yet/)
    pickFile(pdf())
    expect(await screen.findByText('Complete your profile before uploading a resume.')).toBeInTheDocument()
  })
})

describe('suggested skills', () => {
  async function uploaded(skills: SkillsClient, reload = vi.fn(async () => undefined)) {
    mount(resumeClient(), skills, reload)
    await screen.findByText(/No resume yet/)
    pickFile(pdf())
    await screen.findByText('Skills found in your resume')
    return reload
  }

  it('lists the suggestions with every one ticked', async () => {
    await uploaded(skillsClient())
    for (const name of ['Git', 'Python', 'SQL']) {
      expect(screen.getByRole('checkbox', { name })).toBeChecked()
    }
    expect(screen.getByRole('button', { name: 'Add selected (3)' })).toBeEnabled()
  })

  it('adds only the ticked skills, one request at a time, then reloads the profile', async () => {
    const order: string[] = []
    const add = vi.fn(async (id: number) => {
      order.push(`start ${id}`)
      await new Promise(resolve => setTimeout(resolve, 5))
      order.push(`end ${id}`)
    })
    const reload = await uploaded(skillsClient({ add }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'Git' }))
    fireEvent.click(screen.getByRole('button', { name: 'Add selected (2)' }))
    await waitFor(() => expect(reload).toHaveBeenCalledTimes(1))
    expect(order).toEqual(['start 1', 'end 1', 'start 2', 'end 2'])
    expect(add).not.toHaveBeenCalledWith(3)
  })

  it('shows a failed skill as not saved with a retry, and keeps the others saved', async () => {
    let sqlAttempts = 0
    const add = vi.fn(async (id: number) => {
      if (id === 2 && sqlAttempts++ === 0) throw { status: 503, code: 'service_unavailable', message: 'busy' }
    })
    const reload = vi.fn(async () => undefined)
    render(
      <ResumeSection
        confirmedSkills={[]}
        onProfileReload={reload}
        client={resumeClient()}
        skillsClient={skillsClient({ add })}
      />,
    )
    await screen.findByText(/No resume yet/)
    pickFile(pdf())
    await screen.findByText('Skills found in your resume')
    fireEvent.click(screen.getByRole('button', { name: 'Add selected (3)' }))

    const sqlRow = (await screen.findByRole('checkbox', { name: 'SQL' })).closest('li')!
    expect(await within(sqlRow).findByText('Not saved')).toBeInTheDocument()
    expect(add).toHaveBeenCalledTimes(3) // the failure did not stop the others
    expect(reload).toHaveBeenCalledTimes(1)

    fireEvent.click(within(sqlRow).getByRole('button', { name: 'Retry adding SQL' }))
    await waitFor(() => expect(within(sqlRow).queryByText('Not saved')).not.toBeInTheDocument())
    expect(add).toHaveBeenCalledTimes(4)
    expect(reload).toHaveBeenCalledTimes(2)
  })

  it('marks skills that are already confirmed as added', async () => {
    render(
      <ResumeSection
        confirmedSkills={[PYTHON]}
        onProfileReload={vi.fn(async () => undefined)}
        client={resumeClient({ current: vi.fn(async () => resume()) })}
        skillsClient={skillsClient()}
      />,
    )
    const row = (await screen.findByRole('checkbox', { name: 'Python' })).closest('li')!
    expect(within(row).getByText('Added')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add selected (2)' })).toBeInTheDocument()
  })
})

describe('replace resume', () => {
  it('is disabled while "Add selected" is running', async () => {
    const add = vi.fn(() => new Promise<void>(() => {}))
    mount(resumeClient({ current: vi.fn(async () => resume()) }), skillsClient({ add }))
    await screen.findByText('Skills found in your resume')
    fireEvent.click(screen.getByRole('button', { name: 'Add selected (3)' }))
    expect(screen.getByRole('button', { name: 'Replace resume' })).toBeDisabled()
  })
})

describe('overlapping requests', () => {
  it('disables Add selected, per-skill Retry and load Retry while an upload runs', async () => {
    let finish: (value: ResumeResponse) => void = () => {}
    const upload = vi.fn(() => new Promise<ResumeResponse>(resolve => { finish = resolve }))
    const add = vi.fn(async (id: number) => {
      if (id === 2) throw { status: 503, code: 'service_unavailable', message: 'busy' }
    })
    mount(resumeClient({ current: vi.fn(async () => resume()), upload }), skillsClient({ add }))
    await screen.findByText('Skills found in your resume')
    fireEvent.click(screen.getByRole('button', { name: 'Add selected (3)' }))
    await screen.findByRole('button', { name: 'Retry adding SQL' })

    pickFile(pdf())
    await waitFor(() => expect(screen.getByRole('button', { name: 'Retry adding SQL' })).toBeDisabled())
    expect(screen.getByRole('button', { name: /Add selected/ })).toBeDisabled()
    finish(resume({ file_name: 'new.pdf' }))
    expect(await screen.findByText('new.pdf')).toBeInTheDocument()
  })

  it('ignores a stale load that finishes after a newer upload', async () => {
    let settleLoad: (value: ResumeResponse | null) => void = () => {}
    const current = vi.fn(() => new Promise<ResumeResponse | null>(resolve => { settleLoad = resolve }))
    mount(resumeClient({ current, upload: vi.fn(async () => resume({ file_name: 'fresh.pdf' })) }), skillsClient())
    pickFile(pdf())
    expect(await screen.findByText('fresh.pdf')).toBeInTheDocument()
    settleLoad(null) // the older, slower GET answers last
    await new Promise(resolve => setTimeout(resolve, 20))
    expect(screen.getByText('fresh.pdf')).toBeInTheDocument()
    expect(screen.queryByText(/No resume yet/)).not.toBeInTheDocument()
  })
})

describe('skill editor', () => {
  it('is mounted in the section with the supplied skills client', async () => {
    const skills = skillsClient()
    mount(resumeClient(), skills)
    await waitFor(() => expect(skills.search).toHaveBeenCalled())
  })
})
