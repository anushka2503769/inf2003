import { env } from './env'
import type { ApiErrorBody, ApiErrorCode } from '../types/api'

/**
 * The one place the frontend talks to FastAPI.
 *
 * Screens should call the typed helpers in `lib/api.ts` rather than `request`
 * directly, and should never call `fetch` themselves. Keeping every call here
 * means bearer tokens, timeouts, error shapes and 401 handling are solved once.
 */

const DEFAULT_TIMEOUT_MS = 10_000

/* -------------------------------------------------------------------------- */
/* Error type                                                                  */
/* -------------------------------------------------------------------------- */

export class ApiError extends Error {
  readonly status: number
  readonly code: ApiErrorCode
  readonly details?: Record<string, unknown>

  constructor(
    status: number,
    code: ApiErrorCode,
    message: string,
    details?: Record<string, unknown>,
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }

  /** True when retrying the same request could plausibly succeed. */
  get isRetryable(): boolean {
    return this.code === 'network_error' || this.status >= 500 || this.status === 429
  }
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError
}

/**
 * Message safe to render in the interface. Backend messages are written for
 * students; anything unexpected falls back to a plain sentence rather than
 * leaking a stack trace or a raw status line.
 */
export function toDisplayMessage(error: unknown): string {
  if (isApiError(error)) {
    if (error.code === 'network_error') {
      return 'Cannot reach the server. Check that the API is running, then try again.'
    }
    if (error.code === 'internal_error' || error.status >= 500) {
      return 'The server had a problem with that request. Try again in a moment.'
    }
    return error.message
  }
  return 'Something did not work. Try again.'
}

/* -------------------------------------------------------------------------- */
/* Auth wiring                                                                 */
/* -------------------------------------------------------------------------- */

type TokenProvider = () => Promise<string | null>

let getAccessToken: TokenProvider = async () => null
let onUnauthenticated: (() => void) | null = null

/**
 * Called once by the session provider. Injecting the token this way keeps the
 * client free of any import from the auth layer, so `lib/` has no React or
 * Supabase dependency and stays testable on its own.
 */
export function configureApiAuth(options: {
  getAccessToken: TokenProvider
  onUnauthenticated?: () => void
}): void {
  getAccessToken = options.getAccessToken
  onUnauthenticated = options.onUnauthenticated ?? null
}

/* -------------------------------------------------------------------------- */
/* Request                                                                     */
/* -------------------------------------------------------------------------- */

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  /** Serialised as JSON. Omit for GET. */
  body?: unknown
  /** Caller's abort signal; combined with the internal timeout. */
  signal?: AbortSignal
  timeoutMs?: number
  /** Set false for endpoints that must work signed out. Defaults to true. */
  auth?: boolean
  query?: Record<string, string | number | boolean | undefined | null>
}

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const base = env.apiBaseUrl.replace(/\/$/, '')
  const suffix = path.startsWith('/') ? path : `/${path}`
  const url = `${base}${suffix}`
  if (!query) return url

  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== '') {
      params.set(key, String(value))
    }
  }
  const serialised = params.toString()
  return serialised === '' ? url : `${url}?${serialised}`
}

function parseErrorBody(status: number, payload: unknown): ApiError {
  const fallback: ApiErrorCode =
    status === 401
      ? 'unauthenticated'
      : status === 403
        ? 'forbidden'
        : status === 404
          ? 'not_found'
          : status === 409
            ? 'conflict'
            : status === 422
              ? 'validation_failed'
              : status === 429
                ? 'rate_limited'
                : 'internal_error'

  if (
    typeof payload === 'object' &&
    payload !== null &&
    'error' in payload &&
    typeof (payload as ApiErrorBody).error === 'object'
  ) {
    const body = (payload as ApiErrorBody).error
    if (typeof body.message === 'string' && typeof body.code === 'string') {
      return new ApiError(status, body.code, body.message, body.details)
    }
  }

  return new ApiError(status, fallback, `Request failed with status ${status}.`)
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, signal, timeoutMs = DEFAULT_TIMEOUT_MS, auth = true, query } = options

  const headers: Record<string, string> = { Accept: 'application/json' }

  if (auth) {
    const token = await getAccessToken()
    if (token !== null) headers.Authorization = `Bearer ${token}`
  }
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  // AbortSignal.any keeps the caller's cancellation working alongside the timeout.
  const timeout = AbortSignal.timeout(timeoutMs)
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout

  let response: Response
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: combined,
    })
  } catch (cause) {
    if (signal?.aborted) throw cause // the caller cancelled on purpose
    throw new ApiError(0, 'network_error', 'The request did not reach the server.')
  }

  if (response.status === 401) {
    onUnauthenticated?.()
  }

  if (response.status === 204) {
    return undefined as T
  }

  let payload: unknown = null
  const text = await response.text()
  if (text !== '') {
    try {
      payload = JSON.parse(text)
    } catch {
      if (response.ok) {
        throw new ApiError(response.status, 'malformed_response', 'The server sent an unreadable response.')
      }
    }
  }

  if (!response.ok) {
    throw parseErrorBody(response.status, payload)
  }

  return payload as T
}
