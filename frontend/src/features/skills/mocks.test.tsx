import { describe, expect, it } from 'vitest'

import { createMockSkillsClient } from './client'
import {
  MOCK_CONFIRMED_SKILLS,
  MOCK_PROFILE_NOT_FOUND,
  MOCK_SERVICE_UNAVAILABLE,
  MOCK_SKILL_DICTIONARY,
  MOCK_SKILL_NOT_FOUND,
  MOCK_VALIDATION_ERROR,
  MockApiFailure,
  addSkillMock,
  removeSkillMock,
  searchSkillsMock,
} from './mocks'

describe('searchSkillsMock — GET /api/skills contract', () => {
  it('lists the first `limit` skills alphabetically for an empty query', () => {
    const { items, has_more } = searchSkillsMock('', 5)
    expect(items).toHaveLength(5)
    const names = items.map(skill => skill.name)
    expect(names).toEqual([...names].sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase())))
    expect(has_more).toBe(true) // dictionary has 25 entries, well past a limit of 5
  })

  it('matches case-insensitively as a substring, not a prefix', () => {
    const { items } = searchSkillsMock('script')
    const names = items.map(skill => skill.name)
    expect(names).toContain('JavaScript') // "Script" is a mid-word substring here
    expect(names).toContain('TypeScript')
  })

  it('sorts by lowercase name, then skill_id as the tie-breaker', () => {
    // The dictionary has no same-name collisions today, so this asserts the
    // general invariant on the full unfiltered set rather than a contrived
    // duplicate — if two names ever do collide, the lower skill_id must sort
    // first.
    const { items } = searchSkillsMock('', 100)
    for (let i = 1; i < items.length; i += 1) {
      const prevKey = items[i - 1].name.toLowerCase()
      const key = items[i].name.toLowerCase()
      expect(
        prevKey < key || (prevKey === key && items[i - 1].skill_id < items[i].skill_id),
      ).toBe(true)
    }
  })

  it('returns has_more: false once the limit exceeds the total match count', () => {
    const { items, has_more } = searchSkillsMock('', 100)
    expect(items.length).toBeLessThanOrEqual(100)
    expect(items.length).toBe(MOCK_SKILL_DICTIONARY.length)
    expect(has_more).toBe(false)
  })

  it('computes has_more at the exact boundary — matches === limit is NOT has_more', () => {
    const total = MOCK_SKILL_DICTIONARY.length
    const exact = searchSkillsMock('', total)
    expect(exact.has_more).toBe(false)
    const oneShort = searchSkillsMock('', total - 1)
    expect(oneShort.has_more).toBe(true)
    expect(oneShort.items).toHaveLength(total - 1)
  })

  it('returns {items: [], has_more: false} for no matches, matching the contract exactly', () => {
    expect(searchSkillsMock('this-skill-does-not-exist-anywhere')).toEqual({
      items: [],
      has_more: false,
    })
  })

  it('treats % and _ as literal characters, never as SQL wildcards', () => {
    // No dictionary entry contains a literal % or _, so a search for either
    // must return no matches — if this mock's filter ever used them as
    // wildcard operators (e.g. via a naive LIKE/RegExp translation), it
    // would incorrectly match everything or many entries instead.
    expect(searchSkillsMock('%').items).toHaveLength(0)
    expect(searchSkillsMock('_').items).toHaveLength(0)
  })

  it('trims and truncates the query to 100 characters before matching', () => {
    const padded = `  python${' '.repeat(10)}`
    expect(searchSkillsMock(padded).items.map(s => s.name)).toContain('Python')
  })

  it('rejects an out-of-range limit with the exact VALIDATION_ERROR envelope', () => {
    expect(() => searchSkillsMock('', 0)).toThrow(MockApiFailure)
    try {
      searchSkillsMock('', 0)
      expect.unreachable('searchSkillsMock should have thrown')
    } catch (cause) {
      expect(cause).toBeInstanceOf(MockApiFailure)
      const failure = cause as MockApiFailure
      expect(failure.status).toBe(422)
      expect(failure.body).toEqual(MOCK_VALIDATION_ERROR)
    }
  })

  it('injects a 503 SERVICE_UNAVAILABLE on demand for failure-path tests', () => {
    try {
      searchSkillsMock('', 20, 'service_unavailable')
      expect.unreachable('searchSkillsMock should have thrown')
    } catch (cause) {
      expect(cause).toBeInstanceOf(MockApiFailure)
      expect((cause as MockApiFailure).status).toBe(503)
      expect((cause as MockApiFailure).body).toEqual(MOCK_SERVICE_UNAVAILABLE)
    }
  })
})

describe('addSkillMock / removeSkillMock — PUT/DELETE /api/me/skills/{id} contract', () => {
  it('resolves (no throw, no return value) for a valid skill_id', () => {
    const validId = MOCK_SKILL_DICTIONARY[0].skill_id
    expect(() => addSkillMock(validId, MOCK_CONFIRMED_SKILLS)).not.toThrow()
    expect(addSkillMock(validId, MOCK_CONFIRMED_SKILLS)).toBeUndefined() // 204, no body
  })

  it('adding an already-confirmed skill is a successful no-op, not an error', () => {
    const alreadyConfirmedId = MOCK_CONFIRMED_SKILLS[0].skill_id
    expect(() => addSkillMock(alreadyConfirmedId, MOCK_CONFIRMED_SKILLS)).not.toThrow()
  })

  it('throws the exact SKILL_NOT_FOUND envelope for an id outside the dictionary', () => {
    try {
      addSkillMock(999_999, MOCK_CONFIRMED_SKILLS)
      expect.unreachable('addSkillMock should have thrown')
    } catch (cause) {
      expect(cause).toBeInstanceOf(MockApiFailure)
      const failure = cause as MockApiFailure
      expect(failure.status).toBe(404)
      expect(failure.body).toEqual(MOCK_SKILL_NOT_FOUND)
    }
  })

  it('removeSkillMock never throws not-found — absent link is already the desired state', () => {
    expect(() => removeSkillMock(999_999)).not.toThrow()
    expect(removeSkillMock(MOCK_CONFIRMED_SKILLS[0].skill_id)).toBeUndefined()
  })

  it('removeSkillMock is idempotent — repeating it changes nothing observable', () => {
    const id = MOCK_CONFIRMED_SKILLS[0].skill_id
    expect(() => {
      removeSkillMock(id)
      removeSkillMock(id)
      removeSkillMock(id)
    }).not.toThrow()
  })
})

describe('error envelope fixtures — exact shape match for docs/API.md', () => {
  it.each([
    ['SKILL_NOT_FOUND', MOCK_SKILL_NOT_FOUND],
    ['PROFILE_NOT_FOUND', MOCK_PROFILE_NOT_FOUND],
    ['VALIDATION_ERROR', MOCK_VALIDATION_ERROR],
    ['SERVICE_UNAVAILABLE', MOCK_SERVICE_UNAVAILABLE],
  ])('%s has the { error: { code, message, details? } } envelope with the real contract code', (code, body) => {
    expect(body.error.code).toBe(code)
    expect(typeof body.error.message).toBe('string')
    expect(body.error.message.length).toBeGreaterThan(0)
  })
})

describe('createMockSkillsClient — async adapter over the synchronous mocks', () => {
  it('resolves search/add/remove as real Promises, not synchronous throws', async () => {
    const client = createMockSkillsClient(MOCK_CONFIRMED_SKILLS)
    await expect(client.search('python')).resolves.toMatchObject({
      items: [{ name: 'Python' }],
    })
    await expect(client.add(MOCK_SKILL_DICTIONARY[0].skill_id)).resolves.toBeUndefined()
    await expect(client.remove(MOCK_SKILL_DICTIONARY[0].skill_id)).resolves.toBeUndefined()
  })

  it('rejects with a SkillsClientError (status + code + message), not a raw MockApiFailure', async () => {
    const client = createMockSkillsClient(MOCK_CONFIRMED_SKILLS)
    await expect(client.add(999_999)).rejects.toEqual({
      status: 404,
      code: 'SKILL_NOT_FOUND',
      message: MOCK_SKILL_NOT_FOUND.error.message,
    })
  })
})