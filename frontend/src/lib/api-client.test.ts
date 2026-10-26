import { afterEach, describe, expect, it, vi } from 'vitest'

import { configureApiAuth, request } from './api-client'

afterEach(() => {
  vi.unstubAllGlobals()
  configureApiAuth({ getAccessToken: async () => null })
})

function stubFetch(status: number, body: unknown = {}) {
  const fetchMock = vi.fn(
    async () => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('request body handling', () => {
  it('sends FormData as-is without a JSON content type', async () => {
    const fetchMock = stubFetch(200)
    const form = new FormData()
    form.append('file', new File(['x'], 'cv.pdf'))
    await request('/resumes/upload', { method: 'POST', body: form })
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(init.body).toBe(form)
    expect((init.headers as Record<string, string>)['Content-Type']).toBeUndefined()
  })

  it('still sends JSON bodies as JSON', async () => {
    const fetchMock = stubFetch(200)
    await request('/me', { method: 'POST', body: { full_name: 'A' } })
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(init.body).toBe('{"full_name":"A"}')
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json')
  })

  it('sends the bearer token on a form upload and signs out on 401', async () => {
    const onUnauthenticated = vi.fn()
    configureApiAuth({ getAccessToken: async () => 'tok', onUnauthenticated })
    const fetchMock = stubFetch(401, { error: { code: 'unauthenticated', message: 'no' } })
    await expect(request('/resumes/upload', { method: 'POST', body: new FormData() })).rejects.toMatchObject({
      status: 401,
    })
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok')
    expect(onUnauthenticated).toHaveBeenCalledTimes(1)
  })
})
