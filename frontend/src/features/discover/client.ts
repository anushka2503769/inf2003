import type { DiscoverDecision, DiscoverFilters, DiscoverResponse } from './types'

export interface DiscoverClient {
  list(filters: DiscoverFilters, offset: number, limit: number): Promise<DiscoverResponse>
  decide(jobId: string, status: DiscoverDecision): Promise<void>
}

// Real client switch: replace this export with the exact line below.
// export { realDiscoverClient as discoverClient } from './realClient'
export { mockDiscoverClient as discoverClient } from './mocks'
