/**
 * Synthetic, contract-shaped mocks for the skill editor (ANU-01).
 *
 * Shapes here mirror docs/API.md exactly — field names, casing of error
 * codes, envelope structure — so swapping this module out for the real
 * `lib/api.ts` client later (ANU-02, against Jason's live endpoints) is a
 * one-line change in whatever wires `SkillEditor` up, not a data-shape
 * migration. Mock IDs intentionally do NOT match live seed IDs (per task
 * doc), so nothing here can be mistaken for real fixture data.
 */

import type { ApiErrorBody } from '../../types/api'
import type { SkillSearchResponse } from './types'

/* -------------------------------------------------------------------------- */
/* Dictionary — the full synthetic "skills" table this mock searches over     */
/* -------------------------------------------------------------------------- */

/**
 * Deliberately >20 entries and deliberately NOT alphabetically pre-sorted,
 * so `searchSkillsMock` has to do real work to satisfy the contract's
 * "sort by lowercase name, then skill ID" rule instead of accidentally
 * passing because the fixture was already in order.
 */
export const MOCK_SKILL_DICTIONARY: ReadonlyArray<{ skill_id: number; name: string }> = [
  { skill_id: 9001, name: 'React' },
  { skill_id: 9002, name: 'Python' },
  { skill_id: 9003, name: 'SQL' },
  { skill_id: 9004, name: 'TypeScript' },
  { skill_id: 9005, name: 'Docker' },
  { skill_id: 9006, name: 'Kubernetes' },
  { skill_id: 9007, name: 'Figma' },
  { skill_id: 9008, name: 'Java' },
  { skill_id: 9009, name: 'JavaScript' },
  { skill_id: 9010, name: 'Go' },
  { skill_id: 9011, name: 'Rust' },
  { skill_id: 9012, name: 'PostgreSQL' },
  { skill_id: 9013, name: 'MongoDB' },
  { skill_id: 9014, name: 'GraphQL' },
  { skill_id: 9015, name: 'Terraform' },
  { skill_id: 9016, name: 'AWS' },
  { skill_id: 9017, name: 'Azure' },
  { skill_id: 9018, name: 'Google Cloud Platform' },
  { skill_id: 9019, name: 'Node.js' },
  { skill_id: 9020, name: 'Django' },
  { skill_id: 9021, name: 'Flask' },
  { skill_id: 9022, name: 'FastAPI' },
  { skill_id: 9023, name: 'R' },
  { skill_id: 9024, name: 'Tableau' },
  { skill_id: 9025, name: 'Excel' },
]

/** A student who has confirmed a handful of skills, for the default mock story. */
export const MOCK_CONFIRMED_SKILLS: ReadonlyArray<{ skill_id: number; name: string }> = [
  { skill_id: 9002, name: 'Python' },
  { skill_id: 9003, name: 'SQL' },
]

/* -------------------------------------------------------------------------- */
/* Error bodies — exact envelope, verified against Jason's actual backend     */
/* (backend/app/errors.py + routers/skills.py on jason/seedskills, merged     */
/* into dev). Earlier drafts of this file used docs/API.md's uppercase codes */
/* (SKILL_NOT_FOUND, PROFILE_NOT_FOUND, VALIDATION_ERROR, SERVICE_UNAVAILABLE)*/
/* — that doc is stale. The real, live contract is lowercase and reuses a    */
/* single `not_found` code for both a missing profile and a missing skill,  */
/* disambiguated by `details.resource`, matching the frontend's existing    */
/* `ApiErrorCode` union in types/api.ts exactly (no cast needed here).       */
/* -------------------------------------------------------------------------- */

export const MOCK_SKILL_NOT_FOUND: ApiErrorBody = {
  error: {
    code: 'not_found',
    message: 'That skill is no longer in the dictionary.',
    details: { resource: 'skill' },
  },
}

export const MOCK_PROFILE_NOT_FOUND: ApiErrorBody = {
  error: {
    code: 'not_found',
    message: 'You have not set up your profile yet.',
    details: { resource: 'profile' },
  },
}

export const MOCK_VALIDATION_ERROR: ApiErrorBody = {
  error: {
    code: 'validation_failed',
    message: 'Input should be greater than or equal to 1',
    details: { field: 'limit' },
  },
}

export const MOCK_SERVICE_UNAVAILABLE: ApiErrorBody = {
  error: {
    // Real gap, found while typechecking this fix: the backend's error
    // handler (backend/app/errors.py) genuinely emits `service_unavailable`
    // for Mongo/SQL access failures, but the shared `ApiErrorCode` union in
    // types/api.ts does not include it — every other code in this file
    // matches the union exactly with no cast needed; this is the one
    // real exception, not a leftover from the earlier uppercase mistake.
    code: 'service_unavailable' as ApiErrorBody['error']['code'],
    message: 'Document storage is temporarily unavailable.',
  },
}

/* -------------------------------------------------------------------------- */
/* Search — mirrors GET /api/skills exactly, including has_more semantics     */
/* -------------------------------------------------------------------------- */

const SEARCH_LIMIT_DEFAULT = 20
const SEARCH_LIMIT_MAX = 100

/**
 * In-memory stand-in for `GET /api/skills?q=&limit=`.
 *
 * - Empty `q` lists the first `limit` entries alphabetically (contract §GET
 *   /api/skills).
 * - Case-insensitive *substring* match, `%`/`_` treated as literal chars
 *   (there's no LIKE here, so this is naturally satisfied — asserted in
 *   tests so a future rewrite can't silently reintroduce wildcard behaviour).
 * - Sorted by lowercase name, then skill_id as tie-breaker.
 * - `has_more` computed by fetching one extra row past `limit`, exactly as
 *   the contract instructs the backend to.
 * - Throws the exact `MOCK_SERVICE_UNAVAILABLE` / `MOCK_VALIDATION_ERROR`
 *   bodies when asked to, so error-path tests don't need a second mock shape.
 */
export function searchSkillsMock(
  rawQuery: string,
  rawLimit: number = SEARCH_LIMIT_DEFAULT,
  inject?: 'service_unavailable' | 'validation_error',
): SkillSearchResponse {
  if (inject === 'service_unavailable') {
    throw new MockApiFailure(503, MOCK_SERVICE_UNAVAILABLE)
  }

  const q = rawQuery.trim().slice(0, 100)
  const limit = Math.min(Math.max(Math.trunc(rawLimit), 1), SEARCH_LIMIT_MAX)

  if (inject === 'validation_error' || !Number.isFinite(rawLimit) || rawLimit < 1) {
    throw new MockApiFailure(422, MOCK_VALIDATION_ERROR)
  }

  const needle = q.toLowerCase()
  const matches = MOCK_SKILL_DICTIONARY.filter(skill =>
    needle === '' ? true : skill.name.toLowerCase().includes(needle),
  ).sort((a, b) => {
    const byName = a.name.toLowerCase().localeCompare(b.name.toLowerCase())
    return byName !== 0 ? byName : a.skill_id - b.skill_id
  })

  const page = matches.slice(0, limit)
  const has_more = matches.length > limit

  return { items: page.map(({ skill_id, name }) => ({ skill_id, name })), has_more }
}

/* -------------------------------------------------------------------------- */
/* Add / remove — mirrors PUT/DELETE /api/me/skills/{skill_id}                */
/* -------------------------------------------------------------------------- */

/**
 * `PUT /api/me/skills/{skill_id}` mock: 204 (no body) on success, including
 * the "already linked" no-op case; `SKILL_NOT_FOUND` for an ID not in the
 * dictionary at all (distinct from "already confirmed", which is still a
 * success per contract).
 */
export function addSkillMock(
  skillId: number,
  currentlyConfirmed: ReadonlyArray<{ skill_id: number }>,
  inject?: 'not_found' | 'service_unavailable',
): void {
  if (inject === 'service_unavailable') throw new MockApiFailure(503, MOCK_SERVICE_UNAVAILABLE)
  const exists = MOCK_SKILL_DICTIONARY.some(skill => skill.skill_id === skillId)
  if (inject === 'not_found' || !exists) throw new MockApiFailure(404, MOCK_SKILL_NOT_FOUND)
  void currentlyConfirmed // no-op branch is identical to the success branch; nothing to compute
  // 204, no body — caller must not attempt to parse a response here.
}

/**
 * `DELETE /api/me/skills/{skill_id}` mock: always 204, even for an unknown
 * or already-absent ID (contract explicitly makes this idempotent).
 */
export function removeSkillMock(_skillId: number, inject?: 'service_unavailable'): void {
  if (inject === 'service_unavailable') throw new MockApiFailure(503, MOCK_SERVICE_UNAVAILABLE)
  // 204, no body.
}

/* -------------------------------------------------------------------------- */
/* Failure type — lets tests assert on status + exact error body together     */
/* -------------------------------------------------------------------------- */

export class MockApiFailure extends Error {
  readonly status: number
  readonly body: ApiErrorBody

  constructor(status: number, body: ApiErrorBody) {
    super(body.error.message)
    this.name = 'MockApiFailure'
    this.status = status
    this.body = body
  }
}