import type { SkillGapClient, SkillGapClientError, SkillGapResponse, SkillGapRolesResponse } from './types'

export const MOCK_ROLES: SkillGapRolesResponse = { items: [
  { role_category: 'Software Engineering', job_count: 12 },
  { role_category: 'Data Science', job_count: 4 },
  { role_category: 'Unclassified', job_count: 0 },
] }

const fixtures: Record<string, SkillGapResponse> = {
  'Software Engineering': {
    role_category: 'Software Engineering', sample_size: 12,
    skills: [
      { skill_id: 1, name: 'Python', job_count: 9, frequency: .75, required_count: 7, preferred_count: 2, max_minimum_years: 3, years_mentions: 4, user_has: true },
      { skill_id: 2, name: 'React', job_count: 6, frequency: .5, required_count: 4, preferred_count: 2, max_minimum_years: null, years_mentions: 0, user_has: false },
      { skill_id: 3, name: 'SQL', job_count: 3, frequency: .25, required_count: 1, preferred_count: 2, max_minimum_years: 1, years_mentions: 2, user_has: false },
    ], summary: { top_n: 3, user_has_in_top_n: 1 },
  },
  'Data Science': { role_category: 'Data Science', sample_size: 4, skills: [{ skill_id: 4, name: 'Statistics', job_count: 3, frequency: .75, required_count: 2, preferred_count: 1, max_minimum_years: null, years_mentions: 0, user_has: false }], summary: { top_n: 1, user_has_in_top_n: 0 } },
  Unclassified: { role_category: 'Unclassified', sample_size: 0, skills: [], summary: { top_n: 0, user_has_in_top_n: 0 } },
}

const copy = <T,>(value: T): T => structuredClone(value)

export function createMockSkillGapClient(options: {
  roles?: SkillGapRolesResponse
  gapByRole?: Record<string, SkillGapResponse>
  roleError?: SkillGapClientError
  gapError?: SkillGapClientError
  addError?: SkillGapClientError
  latencyMs?: number
} = {}): SkillGapClient {
  const roles = copy(options.roles ?? MOCK_ROLES)
  const data = copy(options.gapByRole ?? fixtures)
  const saved = new Set<number>()
  const delay = <T,>(value: T) => new Promise<T>(resolve => setTimeout(() => resolve(value), options.latencyMs ?? 20))
  return {
    async roles() { await delay(null); if (options.roleError) throw copy(options.roleError); return copy(roles) },
    async forRole(role) {
      await delay(null)
      if (options.gapError) throw copy(options.gapError)
      const result = copy(data[role] ?? { role_category: role, sample_size: 0, skills: [], summary: { top_n: 0, user_has_in_top_n: 0 } })
      result.skills = result.skills.map(skill => ({ ...skill, user_has: skill.user_has || saved.has(skill.skill_id) }))
      result.summary.user_has_in_top_n = result.skills.slice(0, result.summary.top_n).filter(skill => skill.user_has).length
      return result
    },
    async add(skillId) { await delay(null); if (options.addError) throw copy(options.addError); saved.add(skillId) },
  }
}
