import type { TrackerItem, TrackerPage, TrackerStatus, TrackerSummary } from './types'

export interface TrackerClient {
  summary(): Promise<TrackerSummary>
  list(status: TrackerStatus | readonly TrackerStatus[] | undefined, limit: number, offset: number): Promise<TrackerPage>
  update(jobId: string, status: TrackerStatus): Promise<TrackerItem>
  remove(jobId: string): Promise<void>
}
