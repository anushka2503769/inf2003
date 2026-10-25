import { ApiError, request } from '../../lib/api-client'
import type { TrackerClient } from './client'
import type { TrackerItem, TrackerSummary } from './types'

export interface TrackerClientError {
  status: number
  code: string
  message: string
  details?: Record<string, unknown>
}

function toTrackerError(cause: unknown): TrackerClientError {
  if (cause instanceof ApiError) {
    return { status: cause.status, code: cause.code, message: cause.message, details: cause.details }
  }
  return { status: 0, code: 'network_error', message: 'Something did not work. Try again.' }
}

export function createRealTrackerClient(): TrackerClient {
  return {
    async summary() {
      try {
        return await request<TrackerSummary>('/me/jobs/summary')
      } catch (cause) {
        throw toTrackerError(cause)
      }
    },
    async list(status, limit, offset) {
      try {
        const params = new URLSearchParams()
        if (status !== undefined) {
          for (const value of Array.isArray(status) ? status : [status]) params.append('status', value)
        }
        params.set('limit', String(limit))
        params.set('offset', String(offset))
        return await request<{ items: TrackerItem[]; total: number }>(`/me/jobs?${params.toString()}`)
      } catch (cause) {
        throw toTrackerError(cause)
      }
    },
    async update(jobId, status) {
      try {
        return await request<TrackerItem>(`/me/jobs/${encodeURIComponent(jobId)}`, {
          method: 'PUT',
          body: { status },
        })
      } catch (cause) {
        throw toTrackerError(cause)
      }
    },
    async remove(jobId) {
      try {
        await request<void>(`/me/jobs/${encodeURIComponent(jobId)}`, { method: 'DELETE' })
      } catch (cause) {
        throw toTrackerError(cause)
      }
    },
  }
}
