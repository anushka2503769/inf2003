/** Synthetic resume data for VITE_DATA=mock and design QA. No real resumes anywhere. */

import type { MeResponse, Skill } from '../../types/api'
import { MOCK_CONFIRMED_SKILLS, MOCK_SKILL_DICTIONARY } from '../skills/mocks'
import { createMockSkillsClient } from '../skills/client'
import type { SkillsClient } from '../skills/client'
import type { ResumeClient } from './client'
import type { ResumeResponse } from './types'

const LATENCY_MS = 200
const wait = <T,>(value: T) => new Promise<T>(resolve => setTimeout(() => resolve(value), LATENCY_MS))

let stored: ResumeResponse | null = null
const added: Skill[] = []

export const mockResumeClient: ResumeClient = {
  async current() {
    return wait(stored)
  },
  async upload(file) {
    const confirmed = new Set([...MOCK_CONFIRMED_SKILLS, ...added].map(skill => skill.skill_id))
    const suggested = MOCK_SKILL_DICTIONARY.filter(skill => !confirmed.has(skill.skill_id)).slice(0, 5)
    stored = {
      resume_id: 'mock-resume',
      user_id: 'mock-user',
      file_name: file.name,
      uploaded_at: new Date().toISOString(),
      extracted_data: { skills: suggested.map(skill => skill.name), education: [], experience: [], projects: [] },
      suggested_skills: suggested,
    }
    return wait(stored)
  },
}

const baseSkillsClient = createMockSkillsClient()

export const mockSkillsClientForProfile: SkillsClient = {
  ...baseSkillsClient,
  async add(skillId) {
    await baseSkillsClient.add(skillId)
    const skill = MOCK_SKILL_DICTIONARY.find(item => item.skill_id === skillId)
    if (skill && !added.some(item => item.skill_id === skillId)) added.push({ ...skill })
  },
  async remove(skillId) {
    await baseSkillsClient.remove(skillId)
    const index = added.findIndex(item => item.skill_id === skillId)
    if (index >= 0) added.splice(index, 1)
  },
}

export async function mockLoadProfile(): Promise<MeResponse> {
  return wait({
    profile: {
      user_id: 'mock-user',
      full_name: 'Tan Wei Ling',
      created_at: '2026-10-18T09:00:00Z',
      updated_at: '2026-10-18T09:00:00Z',
    },
    onboarding_complete: true,
    skills: [...MOCK_CONFIRMED_SKILLS, ...added].map(skill => ({ ...skill })),
  })
}
