import { afterEach, describe, expect, it, vi } from 'vitest'

import { createRealSkillsClient } from './realClient'

/**
 * Fakes `global.fetch` rather than mocking `skillsApi` or `lib/api-client.ts`
 * — the point of this suite is to prove the full path (`realClient.ts` ->
 * `skillsApi` -> `request()` -> `fetch`) correctly round-trips the actual
 * wire format, not just that the right functions call each other.
 */
function fakeFetch(handler: (url: string, init: RequestInit) => Response): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit) => handler(url, init)),
  )
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('realClient.search — GET /api/skills (via skillsApi)', () => {
  it('sends q and limit as query params and returns the parsed body', async () => {
    let capturedUrl = ''
    fakeFetch(url => {
      capturedUrl = url
      return jsonResponse(200, { items: [{ skill_id: 1, name: 'Python' }], has_more: false })
    })

    const result = await createRealSkillsClient().search('python', 20)

    expect(capturedUrl).toContain('/skills?')
    expect(capturedUrl).toContain('q=python')
    expect(capturedUrl).toContain('limit=20')
    expect(result).toEqual({ items: [{ skill_id: 1, name: 'Python' }], has_more: false })
  })

  it('omits an empty query string entirely, letting the backend default apply', async () => {
    let capturedUrl = ''
    fakeFetch(url => {
      capturedUrl = url
      return jsonResponse(200, { items: [], has_more: false })
    })

    await createRealSkillsClient().search('', 20)

    expect(capturedUrl).not.toContain('q=')
  })

  it('maps a validation_failed 422 into a SkillsClientError with details intact', async () => {
    fakeFetch(() =>
      jsonResponse(422, {
        error: {
          code: 'validation_failed',
          message: 'Unknown query parameter: limlt.',
          details: { field: 'limlt' },
        },
      }),
    )

    await expect(createRealSkillsClient().search('x', 20)).rejects.toEqual({
      status: 422,
      code: 'validation_failed',
      message: 'Unknown query parameter: limlt.',
      details: { field: 'limlt' },
    })
  })
})

describe('realClient.add — PUT /api/me/skills/{id} (via skillsApi)', () => {
  it('resolves to undefined on a real 204 response, without attempting to parse a body', async () => {
    fakeFetch((_url, init) => {
      expect(init.method).toBe('PUT')
      return new Response(null, { status: 204 })
    })

    await expect(createRealSkillsClient().add(9001)).resolves.toBeUndefined()
  })

  it('maps a not_found (resource: skill) 404 into a SkillsClientError', async () => {
    fakeFetch(() =>
      jsonResponse(404, {
        error: {
          code: 'not_found',
          message: 'That skill is no longer in the dictionary.',
          details: { resource: 'skill' },
        },
      }),
    )

    await expect(createRealSkillsClient().add(999_999)).rejects.toEqual({
      status: 404,
      code: 'not_found',
      message: 'That skill is no longer in the dictionary.',
      details: { resource: 'skill' },
    })
  })

  it('maps a not_found (resource: profile) 404 the same way, distinguished only by details', async () => {
    fakeFetch(() =>
      jsonResponse(404, {
        error: {
          code: 'not_found',
          message: 'You have not set up your profile yet.',
          details: { resource: 'profile' },
        },
      }),
    )

    const error = await createRealSkillsClient()
      .add(9001)
      .catch((cause: unknown) => cause)

    expect(error).toEqual({
      status: 404,
      code: 'not_found',
      message: 'You have not set up your profile yet.',
      details: { resource: 'profile' },
    })
  })
})

describe('realClient.remove — DELETE /api/me/skills/{id} (via skillsApi)', () => {
  it('resolves to undefined on 204, the same as a real removal or a no-op', async () => {
    fakeFetch((_url, init) => {
      expect(init.method).toBe('DELETE')
      return new Response(null, { status: 204 })
    })

    await expect(createRealSkillsClient().remove(9001)).resolves.toBeUndefined()
  })

  it('maps a 503 service_unavailable the same way as any other error', async () => {
    fakeFetch(() =>
      jsonResponse(503, {
        error: { code: 'service_unavailable', message: 'Document storage is temporarily unavailable.' },
      }),
    )

    await expect(createRealSkillsClient().remove(9001)).rejects.toEqual({
      status: 503,
      code: 'service_unavailable',
      message: 'Document storage is temporarily unavailable.',
      details: undefined,
    })
  })
})

describe('network failure', () => {
  it('maps a fetch throw to a network_error SkillsClientError, not an uncaught exception', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('Failed to fetch')
      }),
    )

    await expect(createRealSkillsClient().search('x', 20)).rejects.toMatchObject({
      code: 'network_error',
    })
  })
})
