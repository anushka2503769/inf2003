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
    expect((await client.list('SAVED', 20, 0)).total).toBe(0)
    expect((await client.list('APPLIED', 20, 0)).items[0].job.job_id).toBe(savedItem.job.job_id)
    expect((await client.summary()).counts).toMatchObject({ SAVED: 0, APPLIED: 1 })
  })

  it('removes a tracked item idempotently and decrements its status count once', async () => {
    const client = createMockTrackerClient()
    const savedItem = (await client.list('SAVED', 20, 0)).items[0]

    await client.remove(savedItem.job.job_id)
    await client.remove(savedItem.job.job_id)

    expect((await client.summary()).counts.SAVED).toBe(0)
    expect((await client.list('SAVED', 20, 0)).items).toEqual([])
  })
})
