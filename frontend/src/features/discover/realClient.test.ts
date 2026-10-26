import { afterEach, describe, expect, it, vi } from 'vitest'

import { createRealDiscoverClient } from './realClient'

afterEach(() => vi.unstubAllGlobals())

describe('real Discover client', () => {
  it('serializes filters and pagination and returns the response', async () => {
    let url = ''
    vi.stubGlobal('fetch', async (input: RequestInfo | URL) => {
      url = String(input)
      return new Response(JSON.stringify({ items: [], has_more: false }), { status: 200 })
    })

    await createRealDiscoverClient().list({ job_type: 'INTERNSHIP', location: 'Singapore', q: 'data' }, 20, 20)

    expect(url).toContain('/discover?')
    expect(url).toContain('job_type=INTERNSHIP')
    expect(url).toContain('location=Singapore')
    expect(url).toContain('q=data')
    expect(url).toContain('offset=20')
    expect(url).toContain('limit=20')
  })

  it('sends the exact decision payload and maps coded errors with details', async () => {
    let init: RequestInit | undefined
    let url = ''
    vi.stubGlobal('fetch', async (input: RequestInfo | URL, options?: RequestInit) => {
      url = String(input)
      init = options
      return new Response(JSON.stringify({ error: { code: 'not_found', message: 'Profile missing', details: { resource: 'profile' } } }), { status: 404 })
    })

    await expect(createRealDiscoverClient().decide('job-1', 'SAVED')).rejects.toMatchObject({ code: 'not_found', details: { resource: 'profile' } })
    expect(url.endsWith('/api/me/jobs/job-1')).toBe(true)
    expect(init?.method).toBe('PUT')
    expect(init?.body).toBe(JSON.stringify({ status: 'SAVED' }))
  })
})
