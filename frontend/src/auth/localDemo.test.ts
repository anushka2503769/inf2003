import { afterEach, describe, expect, it } from 'vitest'

import {
  DEMO_EMAIL,
  DEMO_USER_ID,
  forgetDemoSignIn,
  loadDemoSession,
  makeDemoSession,
  makeDemoToken,
  rememberDemoSignIn,
} from './localDemo'

function decodePayload(token: string): Record<string, unknown> {
  const part = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
  return JSON.parse(atob(part.padEnd(part.length + ((4 - (part.length % 4)) % 4), '=')))
}

describe('local demo sign-in', () => {
  afterEach(() => forgetDemoSignIn())

  it('carries the claims the backend reads, with a one-day expiry', () => {
    const token = makeDemoToken(1_000)
    expect(token.split('.')).toHaveLength(3)
    const payload = decodePayload(token)
    expect(payload.sub).toBe(DEMO_USER_ID)
    expect(payload.email).toBe(DEMO_EMAIL)
    expect(payload.exp).toBe(1_000 + 24 * 60 * 60)
  })

  it('keeps the signature segment valid base64url (PyJWT decodes it even unverified)', () => {
    const signature = makeDemoToken(1_000).split('.')[2]
    expect(signature).toMatch(/^[A-Za-z0-9_-]+$/)
    expect(signature.length % 4).not.toBe(1)
  })

  it('builds a session for the demo student', () => {
    const session = makeDemoSession()
    expect(session.user.id).toBe(DEMO_USER_ID)
    expect(decodePayload(session.access_token).sub).toBe(DEMO_USER_ID)
  })

  it('remembers the sign-in until sign-out', () => {
    expect(loadDemoSession()).toBeNull()
    rememberDemoSignIn()
    expect(loadDemoSession()?.user.id).toBe(DEMO_USER_ID)
    forgetDemoSignIn()
    expect(loadDemoSession()).toBeNull()
  })
})
