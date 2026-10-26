/**
 * Real resume client, entirely on the shared `request()` (bearer token, 401
 * handling, error envelope). The upload passes FormData, which `request()` sends as-is.
 */

import { ApiError, request } from '../../lib/api-client'
import type { ResumeClient } from './client'
import type { ResumeClientError, ResumeResponse } from './types'

const UPLOAD_TIMEOUT_MS = 30_000

function toClientError(cause: unknown): ResumeClientError {
  if (cause instanceof ApiError) {
    return { status: cause.status, code: cause.code, message: cause.message, details: cause.details }
  }
  return { status: 0, code: 'network_error', message: 'Something did not work. Try again.' }
}

const FALLBACK_MESSAGES: Record<number, string> = {
  413: 'That file is over the 5 MB limit.',
  415: 'Choose a PDF or DOCX file.',
  422: 'That file could not be read. Try a different copy.',
}

export function createRealResumeClient(): ResumeClient {
  return {
    async current() {
      try {
        return await request<ResumeResponse>('/me/resume')
      } catch (cause) {
        if (cause instanceof ApiError && cause.status === 404 && cause.details?.resource === 'resume') {
          return null
        }
        throw toClientError(cause)
      }
    },

    async upload(file) {
      const form = new FormData()
      form.append('file', file)
      try {
        return await request<ResumeResponse>('/resumes/upload', {
          method: 'POST',
          body: form,
          timeoutMs: UPLOAD_TIMEOUT_MS,
        })
      } catch (cause) {
        if (cause instanceof ApiError && cause.code === 'internal_error' && FALLBACK_MESSAGES[cause.status]) {
          throw { ...toClientError(cause), message: FALLBACK_MESSAGES[cause.status] }
        }
        throw toClientError(cause)
      }
    },
  }
}

export const realResumeClient: ResumeClient = createRealResumeClient()
