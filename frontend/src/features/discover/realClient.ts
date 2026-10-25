import { request } from '../../lib/api-client'
import type { ApiError } from '../../lib/api-client'
import type { DiscoverClient } from './client'
import type { DiscoverFilters, DiscoverResponse } from './types'

export interface DiscoverClientError {
  status: number
  code: string
  message: string
  details?: Record<string, unknown>
}

function toDiscoverError(cause: unknown): DiscoverClientError {
  if (cause && typeof cause === 'object' && 'status' in cause && 'code' in cause && 'message' in cause) {
    const error = cause as ApiError
    return { status: error.status, code: error.code, message: error.message, details: error.details }
  }
  return { status: 0, code: 'network_error', message: 'Cannot reach the server. Try again.' }
}

export function createRealDiscoverClient(): DiscoverClient {
  return {
    async list(filters: DiscoverFilters, offset: number, limit: number): Promise<DiscoverResponse> {
      try {
        return await request<DiscoverResponse>('/discover', {
          query: { ...filters, offset, limit },
        })
      } catch (cause) {
        throw toDiscoverError(cause)
      }
    },
    async decide(jobId, status) {
      try {
        await request<void>(`/me/jobs/${encodeURIComponent(jobId)}`, {
          method: 'PUT',
          body: { status },
        })
      } catch (cause) {
        throw toDiscoverError(cause)
      }
    },
  }
}

export const realDiscoverClient: DiscoverClient = createRealDiscoverClient()
