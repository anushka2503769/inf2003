import { afterEach, describe, expect, it, vi } from 'vitest'
import { configureApiAuth } from '../../lib/api-client'
import { createRealSkillGapClient } from './realClient'

afterEach(() => { vi.unstubAllGlobals(); configureApiAuth({ getAccessToken: async () => null }) })
const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })

describe('real skill-gap client uses shared authenticated transport', () => {
  it('gets roles and percent-encodes the selected role query', async () => {
    configureApiAuth({ getAccessToken: async () => 'test-token' })
    const calls: Array<[string, RequestInit]> = []
    vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => { calls.push([url, init]); return json(url.includes('/roles') ? { items: [] } : { role_category: 'R&D / QA', sample_size: 0, skills: [], summary: { top_n: 0, user_has_in_top_n: 0 } }) }))
    const client = createRealSkillGapClient()
    await client.roles()
    await client.forRole('R&D / QA')
    expect(calls[0][0]).toContain('/api/skill-gap/roles')
    expect(calls[0][1].headers).toMatchObject({ Authorization: 'Bearer test-token' })
    expect(calls[1][0]).toContain('role_category=R%26D+%2F+QA')
    expect(calls[1][0]).toContain('limit=30')
  })

  it('uses PUT with no request body, accepts 204, and maps error code/details', async () => {
    const fetchMock = vi.fn(async (_url: string, init: RequestInit) => { expect(init.method).toBe('PUT'); expect(init.body).toBeUndefined(); return new Response(null, { status: 204 }) })
    vi.stubGlobal('fetch', fetchMock)
    await expect(createRealSkillGapClient().add(22)).resolves.toBeUndefined()
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ error: { code: 'not_found', message: 'Missing profile', details: { resource: 'profile' } } }), { status: 404, headers: { 'Content-Type': 'application/json' } })))
    await expect(createRealSkillGapClient().forRole('x')).rejects.toMatchObject({ status: 404, code: 'not_found', details: { resource: 'profile' } })
  })
})
