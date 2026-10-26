import { env } from '../../lib/env'
import { mockDiscoverClient } from './mocks'
import { realDiscoverClient } from './realClient'
import type { DiscoverDecision, DiscoverFilters, DiscoverResponse } from './types'

export interface DiscoverClient {
  list(filters: DiscoverFilters, offset: number, limit: number): Promise<DiscoverResponse>
  decide(jobId: string, status: DiscoverDecision): Promise<void>
}

// The real API by default; VITE_DATA=mock switches to synthetic data.
export const discoverClient: DiscoverClient = env.useMockData ? mockDiscoverClient : realDiscoverClient
