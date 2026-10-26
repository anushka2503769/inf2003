import { afterEach, describe, expect, it, vi } from 'vitest'

afterEach(() => {
  vi.unstubAllEnvs()
  vi.resetModules()
})

async function loadClients() {
  const [discover, discoverMocks, discoverReal, tracker, skillGap, env] = await Promise.all([
    import('../features/discover/client'),
    import('../features/discover/mocks'),
    import('../features/discover/realClient'),
    import('../features/tracker/defaultClient'),
    import('../features/skill-gap/activeClient'),
    import('./env'),
  ])
  return { discover, discoverMocks, discoverReal, tracker, skillGap, env }
}

describe('data source switch', () => {
  it('uses the real API clients by default', async () => {
    vi.stubEnv('VITE_DATA', '')
    const { discover, discoverReal, env } = await loadClients()
    expect(env.env.useMockData).toBe(false)
    expect(discover.discoverClient).toBe(discoverReal.realDiscoverClient)
  })

  it('uses synthetic data on all three screens when VITE_DATA=mock', async () => {
    vi.stubEnv('VITE_DATA', 'mock')
    const { discover, discoverMocks, tracker, skillGap, env } = await loadClients()
    expect(env.env.useMockData).toBe(true)
    expect(discover.discoverClient).toBe(discoverMocks.mockDiscoverClient)
    // The mock tracker and skill-gap clients answer without any network call.
    vi.stubGlobal('fetch', vi.fn(() => { throw new Error('mock mode must not call the API') }))
    await expect(tracker.trackerClient.summary()).resolves.toBeTruthy()
    await expect(skillGap.skillGapClient.roles()).resolves.toBeTruthy()
    vi.unstubAllGlobals()
  })
})
