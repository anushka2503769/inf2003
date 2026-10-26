import { env } from '../../lib/env'
import type { TrackerClient } from './client'
import { createMockTrackerClient } from './mocks'
import { createRealTrackerClient } from './realClient'

// The real API by default; VITE_DATA=mock switches to synthetic data.
export const trackerClient: TrackerClient = env.useMockData ? createMockTrackerClient() : createRealTrackerClient()
