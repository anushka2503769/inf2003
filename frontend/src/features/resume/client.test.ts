import { afterEach, describe, expect, it, vi } from 'vitest'

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
  vi.resetModules()
})

async function load() {
  const [client, mocks, real, skillsReal, skillsMocks] = await Promise.all([
    import('./client'),
    import('./mocks'),
    import('./realClient'),
    import('../skills/realClient'),
    import('../skills/mocks'),
  ])
  return { client, mocks, real, skillsReal, skillsMocks }
}

describe('resume data source', () => {
  it('uses the real clients outside mock mode', async () => {
    vi.stubEnv('VITE_DATA', '')
    const { client, real, skillsReal } = await load()
    expect(client.resumeClient).toBe(real.realResumeClient)
    expect(client.profileSkillsClient).toBe(skillsReal.realSkillsClient)
  })

  it('uses synthetic clients when VITE_DATA=mock, without any network call', async () => {
    vi.stubEnv('VITE_DATA', 'mock')
    vi.stubGlobal('fetch', vi.fn(() => { throw new Error('mock mode must not call the API') }))
    const { client, mocks } = await load()
    expect(client.resumeClient).toBe(mocks.mockResumeClient)
    await expect(client.resumeClient.current()).resolves.toBeNull()
    await expect(client.loadProfile()).resolves.toMatchObject({ onboarding_complete: true })
  })
})

describe('real resume client', () => {
  function respond(status: number, body: unknown) {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }),
    )
    vi.stubGlobal('fetch', fetchMock)
    return fetchMock
  }

  it('treats 404 resource "resume" as no resume yet', async () => {
    respond(404, { error: { code: 'not_found', message: 'none', details: { resource: 'resume' } } })
    const { real } = await load()
    await expect(real.createRealResumeClient().current()).resolves.toBeNull()
  })

  it('surfaces other errors from current()', async () => {
    respond(503, { error: { code: 'service_unavailable', message: 'down' } })
    const { real } = await load()
    await expect(real.createRealResumeClient().current()).rejects.toMatchObject({ status: 503 })
  })

  it('posts the file as multipart to /resumes/upload', async () => {
    const fetchMock = respond(200, { resume_id: 'r1', file_name: 'cv.pdf', suggested_skills: [] })
    const { real } = await load()
    const result = await real.createRealResumeClient().upload(new File(['x'], 'cv.pdf'))
    expect(result.resume_id).toBe('r1')
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toMatch(/\/resumes\/upload$/)
    expect(init.method).toBe('POST')
    expect(init.body).toBeInstanceOf(FormData)
    expect((init.body as FormData).get('file')).toBeInstanceOf(File)
  })

  it('turns an error response into a client error carrying the server message', async () => {
    respond(404, { error: { code: 'not_found', message: 'Complete your profile.', details: { resource: 'profile' } } })
    const { real } = await load()
    await expect(real.createRealResumeClient().upload(new File(['x'], 'cv.pdf'))).rejects.toMatchObject({
      status: 404,
      message: 'Complete your profile.',
      details: { resource: 'profile' },
    })
  })
})
