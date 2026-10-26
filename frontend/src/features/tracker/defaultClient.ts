import type { TrackerClient } from './client'
import { createMockTrackerClient as createTrackerClient } from './mocks'

// Swap this one line to createRealTrackerClient() when WP-2 is available on dev.
export const trackerClient: TrackerClient = createTrackerClient()
