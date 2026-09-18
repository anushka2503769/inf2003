/**
 * Async client interface for the skill editor.
 *
 * `SkillEditor` depends only on `SkillsClient` below, never on `mocks.ts`
 * directly. That is deliberate: ANU-02 ("use the common authenticated
 * client") should be a one-line swap — construct an adapter that calls
 * `lib/api.ts`'s (extended) `skillsApi` and translates its `ApiError` into
 * `SkillsClientError`, then pass it as the `client` prop — with zero changes
 * inside `SkillEditor.tsx` itself.
 */

import type { Skill } from '../../types/api'
import type { SkillSearchResponse } from './types'
import { MockApiFailure, addSkillMock, removeSkillMock, searchSkillsMock } from './mocks'

/** Deliberately narrower than the shared `ApiError` class — just what UI needs. */
export interface SkillsClientError {
  status: number
  code: string
  message: string
}

export function isSkillsClientError(value: unknown): value is SkillsClientError {
  return (
    typeof value === 'object' &&
    value !== null &&
    'status' in value &&
    'code' in value &&
    'message' in value
  )
}

export interface SkillsClient {
  search(query: string, limit?: number): Promise<SkillSearchResponse>
  /** Resolves on 204, including the "already linked" no-op case. Never returns a body. */
  add(skillId: number): Promise<void>
  /** Resolves on 204, including "was never linked". Always safe to repeat. */
  remove(skillId: number): Promise<void>
}

function toClientError(cause: unknown): SkillsClientError {
  if (cause instanceof MockApiFailure) {
    return { status: cause.status, code: cause.body.error.code, message: cause.body.error.message }
  }
  return { status: 0, code: 'network_error', message: 'Something did not work. Try again.' }
}

// Mocks are synchronous; a small artificial delay keeps loading/pending UI
// states honest in manual testing instead of resolving instantly every time.
const MOCK_LATENCY_MS = 150

function delay<T>(value: T): Promise<T> {
  return new Promise(resolve => setTimeout(() => resolve(value), MOCK_LATENCY_MS))
}

/**
 * Wraps the synchronous fixtures in `mocks.ts` behind the same async shape
 * the real client will expose. `confirmed` only matters for the mock's
 * internal no-op bookkeeping and is never required by the interface itself.
 */
export function createMockSkillsClient(confirmed: ReadonlyArray<Skill> = []): SkillsClient {
  return {
    async search(query, limit) {
      try {
        return await delay(searchSkillsMock(query, limit))
      } catch (cause) {
        throw await delay(toClientError(cause))
      }
    },
    async add(skillId) {
      try {
        addSkillMock(skillId, confirmed)
        await delay(undefined)
      } catch (cause) {
        throw await delay(toClientError(cause))
      }
    },
    async remove(skillId) {
      try {
        removeSkillMock(skillId)
        await delay(undefined)
      } catch (cause) {
        throw await delay(toClientError(cause))
      }
    },
  }
}

/** Default client used when no `client` prop is supplied (demos, Storybook-less manual testing). */
export const mockSkillsClient: SkillsClient = createMockSkillsClient()