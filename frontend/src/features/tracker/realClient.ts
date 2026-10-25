import { request } from '../../lib/api-client'
import type { TrackerClient } from './client'
import type { TrackerItem, TrackerSummary } from './types'

/** Adapter over the shared authenticated request; ApiError metadata passes through unchanged. */
export function createRealTrackerClient(): TrackerClient {
  return {
    summary() {
      return request<TrackerSummary>('/me/jobs/summary')
    },
    list(status, limit, offset) {
      const params = new URLSearchParams()
      if (status !== undefined) {
        for (const value of Array.isArray(status) ? status : [status]) params.append('status', value)
      }
      params.set('limit', String(limit))
      params.set('offset', String(offset))
      return request<{ items: TrackerItem[]; total: number }>(`/me/jobs?${params.toString()}`)
    },
    update(jobId, status) {
      return request<TrackerItem>(`/me/jobs/${encodeURIComponent(jobId)}`, {
        method: 'PUT',
        body: { status },
      })
    },
    remove(jobId) {
      return request<void>(`/me/jobs/${encodeURIComponent(jobId)}`, { method: 'DELETE' })
    },
  }
}
