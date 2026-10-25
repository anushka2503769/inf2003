import { afterEach, describe, expect, it, vi } from 'vitest'

import { createRealTrackerClient } from './realClient'

function fakeFetch(handler: (url: string, init: RequestInit) => Response): void {
  vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => handler(url, init)))
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

afterEach(() => vi.unstubAllGlobals())

describe('real tracker client', () => {
  it('keeps repeated status filters and page parameters in the list request', async () => {
    let capturedUrl = ''
    fakeFetch(url => {
      capturedUrl = url
      return jsonResponse(200, { items: [], total: 0 })
    })

    await createRealTrackerClient().list(['SAVED', 'APPLIED'], 20, 40)

    const query = new URL(capturedUrl, 'http://local').searchParams
    expect(query.getAll('status')).toEqual(['SAVED', 'APPLIED'])
    expect(query.get('limit')).toBe('20')
    expect(query.get('offset')).toBe('40')
  })

  it('sends the exact status body on PUT and returns the tracker item', async () => {
    const expected = {
      job: {
        job_id: 'job-1', title: 'Engineer', company_name: 'Example', location: null,
        job_type: null, work_arrangement: null, application_url: 'https://example.test',
        source: 'synthetic', source_posted_at: null, is_active: true,
      },
      status: 'APPLIED', created_at: '2026-10-25T00:00:00Z', updated_at: '2026-10-26T00:00:00Z',
    }
    let requestInit: RequestInit | undefined
    fakeFetch((_url, init) => {
      requestInit = init
      return jsonResponse(200, expected)
    })

    await expect(createRealTrackerClient().update('job-1', 'APPLIED')).resolves.toEqual(expected)
    expect(requestInit?.method).toBe('PUT')
    expect(requestInit?.body).toBe(JSON.stringify({ status: 'APPLIED' }))
  })

  it('treats DELETE 204 as success without parsing a response body', async () => {
    fakeFetch((_url, init) => {
      expect(init.method).toBe('DELETE')
      return new Response(null, { status: 204 })
    })

    await expect(createRealTrackerClient().remove('job-1')).resolves.toBeUndefined()
  })

  it('preserves the shared API error code and resource details', async () => {
    fakeFetch(() => jsonResponse(404, {
      error: { code: 'not_found', message: 'Job not found.', details: { resource: 'job' } },
    }))

    await expect(createRealTrackerClient().update('missing', 'SAVED')).rejects.toEqual({
      status: 404, code: 'not_found', message: 'Job not found.', details: { resource: 'job' },
    })
  })
})
