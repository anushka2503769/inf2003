import { describe, expect, it } from 'vitest'

import { createMockTrackerClient } from './mocks'

describe('stateful tracker mock', () => {
  it('updates status, list membership, and summary counts together', async () => {
    const client = createMockTrackerClient()
    const before = await client.list('SAVED', 20, 0)
    const savedItem = before.items[0]
    expect(savedItem.status).toBe('SAVED')

    const changed = await client.update(savedItem.job.job_id, 'APPLIED')

    expect(changed.status).toBe('APPLIED')
    expect((await client.list('SAVED', 40, 0)).total).toBe(22)
    expect((await client.list('APPLIED', 20, 0)).items[0].job.job_id).toBe(savedItem.job.job_id)
    expect((await client.summary()).counts).toMatchObject({ SAVED: 22, APPLIED: 1 })
  })

  it('removes a tracked item idempotently and decrements its status count once', async () => {
    const client = createMockTrackerClient()
    const savedItem = (await client.list('SAVED', 20, 0)).items[0]

    await client.remove(savedItem.job.job_id)
    await client.remove(savedItem.job.job_id)

    expect((await client.summary()).counts.SAVED).toBe(22)
    expect((await client.list('SAVED', 30, 0)).items).toHaveLength(22)
  })
})


describe('tracker PUT contract in the mock', () => {
  it('creates a decision for a known active job that was not tracked yet', async () => {
    const client = createMockTrackerClient()
    const prior = await client.summary()
    const created = await client.update('90000000-0000-4000-8000-000000000001', 'SAVED')

    expect(created.status).toBe('SAVED')
    expect(created.job.is_active).toBe(true)
    expect((await client.summary()).counts.SAVED).toBe(prior.counts.SAVED + 1)
  })

  it('advances updated_at when a PUT changes status', async () => {
    const client = createMockTrackerClient()
    const before = (await client.list('SAVED', 1, 0)).items[0]
    const changed = await client.update(before.job.job_id, 'APPLIED')

    expect(changed.updated_at).not.toBe(before.updated_at)
  })

  it('does not change updated_at for a same-status PUT', async () => {
    const client = createMockTrackerClient()
    const before = (await client.list('SAVED', 1, 0)).items[0]
    const repeated = await client.update(before.job.job_id, 'SAVED')

    expect(repeated.updated_at).toBe(before.updated_at)
  })

  it('rejects unknown and inactive jobs as not_found job resources', async () => {
    const client = createMockTrackerClient()

    await expect(client.update('90000000-0000-4000-8000-000000000099', 'SAVED')).rejects.toMatchObject({
      status: 404, code: 'not_found', details: { resource: 'job' },
    })
    await expect(client.update('90000000-0000-4000-8000-000000000002', 'SAVED')).rejects.toMatchObject({
      status: 404, code: 'not_found', details: { resource: 'job' },
    })
  })

  it('seeds more than one page of synthetic SAVED rows', async () => {
    const client = createMockTrackerClient()
    const firstPage = await client.list('SAVED', 20, 0)

    expect(firstPage.items).toHaveLength(20)
    expect(firstPage.total).toBeGreaterThan(20)
  })
})
