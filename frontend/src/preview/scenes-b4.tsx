import { useEffect, useRef, type ReactNode } from 'react'
import { Route, Routes } from 'react-router-dom'

import { AppShell } from '../app/AppShell'
import { routes } from '../app/routes'
import type { SkillGapClient, SkillGapResponse, SkillGapRole, SkillGapRow } from '../features/skill-gap/types'
import type { SkillsClient } from '../features/skills/client'
import { SkillEditor } from '../features/skills/SkillEditor'
import { ProfileScreen } from '../screens/ProfileScreen'
import { SkillGapScreen } from '../screens/SkillGapScreen'
import type { Skill } from '../types/api'
import type { PreviewScene } from './types'

/*
 * Preview scenes for Skill Gap and Profile (redesign B4). Dev-only: the
 * harness is lazily imported behind import.meta.env.DEV, so none of this
 * reaches `npm run build`. Data mirrors the hand-off (scratchpad design/src).
 */

const GROUP = 'B4 Skill Gap + Profile'

function InShell({ content }: { content: ReactNode }) {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="*" element={content} />
      </Route>
    </Routes>
  )
}

/**
 * Drives the real screen into a state the way a student would: each step
 * runs once its target exists (polled), in order. Used because Skill Gap
 * deliberately fetches nothing until a role is picked.
 */
function Steps({ steps, children }: { steps: Array<() => boolean>; children: ReactNode }) {
  const script = useRef(steps)
  useEffect(() => {
    const all = script.current
    let index = 0
    const timer = window.setInterval(() => {
      while (index < all.length && all[index]()) index += 1
      if (index >= all.length) window.clearInterval(timer)
    }, 30)
    return () => window.clearInterval(timer)
  }, [])
  return <>{children}</>
}

function setNativeValue(element: HTMLInputElement | HTMLSelectElement, value: string, event: 'input' | 'change') {
  const prototype = element instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype
  Object.getOwnPropertyDescriptor(prototype, 'value')?.set?.call(element, value)
  element.dispatchEvent(new Event(event, { bubbles: true }))
}

const pickRole = (role: string) => () => {
  const select = document.querySelector<HTMLSelectElement>('#skill-gap-role')
  if (!select) return false
  setNativeValue(select, role, 'change')
  return true
}

const tick = (skill: string) => () => {
  const row = Array.from(document.querySelectorAll('.skill-gap__row')).find(
    item => item.querySelector('.skill-gap__name')?.textContent === skill,
  )
  const box = row?.querySelector<HTMLInputElement>('.skill-gap__confirm input')
  if (!box) return false
  box.click()
  return true
}

const focusRole = () => {
  const select = document.querySelector<HTMLSelectElement>('#skill-gap-role')
  if (!select) return false
  select.focus()
  return true
}

const typeInto = (selector: string, value: string) => () => {
  const input = document.querySelector<HTMLInputElement>(selector)
  if (!input) return false
  setNativeValue(input, value, 'input')
  return true
}

const clickSelector = (selector: string) => () => {
  const element = document.querySelector<HTMLElement>(selector)
  if (!element) return false
  element.click()
  return true
}

/* ------------------------------------------------------------------ skill gap fakes */

const B4_ROLES: SkillGapRole[] = [
  { role_category: 'Software Engineering', job_count: 96 },
  { role_category: 'Unclassified', job_count: 61 },
  { role_category: 'Data Science / Analytics', job_count: 42 },
  { role_category: 'Marketing', job_count: 38 },
  { role_category: 'Finance / Accounting', job_count: 35 },
  { role_category: 'Operations', job_count: 29 },
  { role_category: 'Business Development', job_count: 22 },
  { role_category: 'Product Management', job_count: 14 },
  { role_category: 'Human Resources', job_count: 9 },
  { role_category: 'UX / Design', job_count: 4 },
]

type GapSeed = [name: string, count: number, required: number, preferred: number, years: [number, number] | null, has: boolean]

function gapResponse(role: string, sample: number, seeds: GapSeed[]): SkillGapResponse {
  const skills: SkillGapRow[] = seeds.map(([name, count, required, preferred, years, has], index) => ({
    skill_id: 7000 + index + role.length * 50,
    name,
    job_count: count,
    frequency: sample ? count / sample : 0,
    required_count: required,
    preferred_count: preferred,
    max_minimum_years: years ? years[0] : null,
    years_mentions: years ? years[1] : 0,
    user_has: has,
  }))
  const top = Math.min(10, skills.length)
  return {
    role_category: role,
    sample_size: sample,
    skills,
    summary: { top_n: top, user_has_in_top_n: skills.slice(0, top).filter(skill => skill.user_has).length },
  }
}

const B4_GAPS: Record<string, SkillGapResponse> = {
  'Data Science / Analytics': gapResponse('Data Science / Analytics', 42, [
    ['Python', 31, 24, 7, null, true],
    ['SQL', 28, 21, 7, null, true],
    ['Machine Learning', 22, 14, 8, [2, 5], false],
    ['Statistics', 18, 12, 6, null, false],
    ['Tableau', 15, 6, 9, null, false],
    ['Microsoft Excel', 14, 9, 5, null, true],
    ['Power BI', 11, 4, 7, null, false],
    ['Data Visualization', 10, 3, 7, null, false],
    ['R', 9, 5, 4, [1, 3], false],
    ['Communication', 8, 2, 6, null, false],
  ]),
  'UX / Design': gapResponse('UX / Design', 4, [
    ['Figma', 4, 4, 0, null, true],
    ['User Research', 3, 2, 1, null, false],
    ['Prototyping', 3, 1, 2, null, true],
    ['Adobe Illustrator', 2, 0, 2, null, false],
    ['HTML', 1, 0, 1, null, false],
  ]),
  'Human Resources': gapResponse('Human Resources', 9, []),
}

function fakeGapClient({
  roles = B4_ROLES,
  gap = 'ok',
  add = 'ok',
}: {
  roles?: SkillGapRole[] | 'pending'
  gap?: 'ok' | 'pending' | 'error' | 'profile-missing'
  add?: 'ok' | 'error'
} = {}): SkillGapClient {
  const wait = <T,>(value: T) => new Promise<T>(resolve => window.setTimeout(() => resolve(value), 40))
  return {
    roles: () => (roles === 'pending' ? new Promise(() => {}) : wait({ items: roles })),
    forRole: async role => {
      if (gap === 'pending') return new Promise(() => {})
      await wait(null)
      if (gap === 'error') {
        throw { status: 504, code: 'timeout', message: 'The server did not answer in time. Your profile is fine.' }
      }
      if (gap === 'profile-missing') {
        throw { status: 404, code: 'not_found', message: 'We could not find your profile.', details: { resource: 'profile' } }
      }
      return structuredClone(B4_GAPS[role] ?? gapResponse(role, 0, []))
    },
    add: async () => {
      await wait(null)
      if (add === 'error') throw { status: 503, code: 'service_unavailable', message: 'That did not save. The server is busy; try again.' }
    },
  }
}

const gapScreen = (client: SkillGapClient) => <InShell content={<SkillGapScreen client={client} />} />

/* ------------------------------------------------------------------ skills fakes */

const DICTIONARY: Skill[] = [
  'Adobe Illustrator', 'Communication', 'Data Visualization', 'Figma', 'Git', 'Java', 'Machine Learning',
  'Microsoft Excel', 'Power BI', 'PowerPoint', 'PowerShell', 'Python', 'R', 'SQL', 'Statistics', 'Tableau',
].map((name, index) => ({ skill_id: 9000 + index, name }))

const MY_SKILLS = DICTIONARY.filter(skill =>
  ['Figma', 'Git', 'Java', 'Microsoft Excel', 'Python', 'SQL'].includes(skill.name),
)

const fakeSkillsClient: SkillsClient = {
  search: async query => {
    const needle = query.trim().toLowerCase()
    const items = DICTIONARY.filter(skill => skill.name.toLowerCase().startsWith(needle))
    return { items: items.slice(0, 8), has_more: items.length > 8 }
  },
  add: async () => {},
  remove: async () => {},
}

function SkillEditorPreview() {
  return (
    <div className="profile">
      <section className="profile__section">
        <SkillEditor confirmedSkills={MY_SKILLS} onProfileReload={async () => {}} client={fakeSkillsClient} />
      </section>
    </div>
  )
}

/* ------------------------------------------------------------------ scenes */

export const b4Scenes: PreviewScene[] = [
  {
    id: 'skill-gap-pick-a-role',
    title: 'Skill Gap, pick a role (nothing fetched yet)',
    group: GROUP,
    path: routes.skillGap,
    reference: 'skill-gap-pick-a-role.png',
    element: gapScreen(fakeGapClient()),
  },
  {
    id: 'skill-gap-role-picker-open',
    title: 'Skill Gap, role picker focused (native select; its list is drawn by the OS)',
    group: GROUP,
    path: routes.skillGap,
    reference: 'skill-gap-role-picker-open.png',
    element: <Steps steps={[focusRole]}>{gapScreen(fakeGapClient())}</Steps>,
  },
  {
    id: 'skill-gap-loaded',
    title: 'Skill Gap, loaded (Statistics ticked)',
    group: GROUP,
    path: routes.skillGap,
    reference: 'skill-gap-loaded.png',
    element: <Steps steps={[pickRole('Data Science / Analytics'), tick('Statistics')]}>{gapScreen(fakeGapClient())}</Steps>,
  },
  {
    id: 'skill-gap-loading',
    title: 'Skill Gap, counting skills',
    group: GROUP,
    path: routes.skillGap,
    reference: 'skill-gap-loading.png',
    element: <Steps steps={[pickRole('Data Science / Analytics')]}>{gapScreen(fakeGapClient({ gap: 'pending' }))}</Steps>,
  },
  {
    id: 'skill-gap-small-sample',
    title: 'Skill Gap, small sample (4 postings)',
    group: GROUP,
    path: routes.skillGap,
    reference: 'skill-gap-small-sample.png',
    element: <Steps steps={[pickRole('UX / Design')]}>{gapScreen(fakeGapClient())}</Steps>,
  },
  {
    id: 'skill-gap-error',
    title: 'Skill Gap, counts did not load',
    group: GROUP,
    path: routes.skillGap,
    reference: 'skill-gap-error.png',
    element: <Steps steps={[pickRole('Data Science / Analytics')]}>{gapScreen(fakeGapClient({ gap: 'error' }))}</Steps>,
  },
  {
    id: 'skill-gap-no-roles',
    title: 'Skill Gap, no roles yet',
    group: GROUP,
    path: routes.skillGap,
    reference: 'skill-gap-no-roles.png',
    element: gapScreen(fakeGapClient({ roles: [] })),
  },
  {
    id: 'skill-gap-zero-requirements',
    title: 'Skill Gap, role with no readable requirements',
    group: GROUP,
    path: routes.skillGap,
    reference: 'skill-gap-zero-requirements.png',
    element: <Steps steps={[pickRole('Human Resources')]}>{gapScreen(fakeGapClient())}</Steps>,
  },
  {
    id: 'skill-gap-add-failed',
    title: 'Skill Gap, add to my skills failed (inline retry)',
    group: GROUP,
    path: routes.skillGap,
    element: (
      <Steps
        steps={[
          pickRole('Data Science / Analytics'),
          tick('Statistics'),
          () => {
            const row = Array.from(document.querySelectorAll('.skill-gap__row')).find(
              item => item.querySelector('.skill-gap__name')?.textContent === 'Statistics',
            )
            const button = row?.querySelector<HTMLButtonElement>('.skill-gap__side .btn--accent')
            if (!button) return false
            button.click()
            return true
          },
        ]}
      >
        {gapScreen(fakeGapClient({ add: 'error' }))}
      </Steps>
    ),
  },
  {
    id: 'skill-gap-profile-missing',
    title: 'Skill Gap, profile missing (link to onboarding)',
    group: GROUP,
    path: routes.skillGap,
    element: <Steps steps={[pickRole('Data Science / Analytics')]}>{gapScreen(fakeGapClient({ gap: 'profile-missing' }))}</Steps>,
  },
  {
    id: 'skill-gap-loading-roles',
    title: 'Skill Gap, loading roles',
    group: GROUP,
    path: routes.skillGap,
    element: gapScreen(fakeGapClient({ roles: 'pending' })),
  },
  {
    id: 'profile-default',
    title: 'Profile, default (resume and skills not built yet)',
    group: GROUP,
    path: routes.profile,
    reference: 'profile-default.png',
    element: <InShell content={<ProfileScreen />} />,
  },
  {
    id: 'profile-name-edited',
    title: 'Profile, name edited (Save name enabled)',
    group: GROUP,
    path: routes.profile,
    element: (
      <Steps steps={[typeInto('.profile__name-form input', 'Tan Wei Ling Wendy')]}>
        <InShell content={<ProfileScreen />} />
      </Steps>
    ),
  },
  {
    id: 'profile-name-error',
    title: 'Profile, name left empty',
    group: GROUP,
    path: routes.profile,
    element: (
      <Steps steps={[typeInto('.profile__name-form input', '')]}>
        <InShell content={<ProfileScreen />} />
      </Steps>
    ),
  },
  {
    id: 'profile-save-failed',
    title: 'Profile, saving the name failed',
    group: GROUP,
    path: routes.profile,
    profile: {
      renameProfile: async () => {
        throw new Error('preview: rename failed')
      },
    },
    element: (
      <Steps
        steps={[typeInto('.profile__name-form input', 'Tan Wei Ling Wendy'), clickSelector('.profile__name-form button[type="submit"]')]}
      >
        <InShell content={<ProfileScreen />} />
      </Steps>
    ),
  },
  {
    id: 'profile-skill-editor',
    title: 'Skill editor (not yet mounted on Profile), searching "pow"',
    group: GROUP,
    path: routes.profile,
    reference: 'profile-default.png',
    element: (
      <Steps steps={[typeInto('.skill-editor input', 'pow')]}>
        <InShell content={<SkillEditorPreview />} />
      </Steps>
    ),
  },
]
