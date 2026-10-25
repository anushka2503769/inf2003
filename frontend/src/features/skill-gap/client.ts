import type { SkillGapClient, SkillGapClientError } from './types'
import { createMockSkillGapClient } from './mocks'

export function isSkillGapClientError(value: unknown): value is SkillGapClientError {
  return typeof value === 'object' && value !== null && 'status' in value && 'code' in value && 'message' in value
}
export function createDefaultSkillGapClient(): SkillGapClient { return createMockSkillGapClient() }
