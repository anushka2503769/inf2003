import type { ReactNode } from 'react'
import type { Session } from '@supabase/supabase-js'

import { ProfileContext, type ProfileContextValue } from '../auth/ProfileProvider'
import { SessionContext, type SessionContextValue } from '../auth/SessionProvider'
import type { Profile } from '../types/api'

/**
 * Fake session and profile for the dev-only preview harness. Nothing here
 * talks to Supabase or the API; every action resolves immediately.
 */

export const PREVIEW_USER = {
  name: 'Tan Wei Ling',
  email: 'weiling.tan@u.nus.edu',
}

const noop = async () => {}

const fakeSession = {
  access_token: 'preview-token',
  token_type: 'bearer',
  user: { id: '00000000-0000-4000-8000-000000000001', email: PREVIEW_USER.email, user_metadata: {} },
} as unknown as Session

export const PREVIEW_PROFILE: Profile = {
  user_id: '00000000-0000-4000-8000-000000000001',
  full_name: PREVIEW_USER.name,
  created_at: '2026-10-18T09:00:00Z',
  updated_at: '2026-10-18T09:00:00Z',
}

export function fakeSessionValue(overrides: Partial<SessionContextValue> = {}): SessionContextValue {
  return {
    status: 'signed-in',
    session: fakeSession,
    identity: { email: PREVIEW_USER.email, suggestedName: null, avatarUrl: null },
    signInWithGoogle: noop,
    signOut: noop,
    ...overrides,
  }
}

export function fakeProfileValue(overrides: Partial<ProfileContextValue> = {}): ProfileContextValue {
  return {
    status: 'ready',
    profile: PREVIEW_PROFILE,
    onboardingComplete: true,
    error: null,
    reload: noop,
    createProfile: noop,
    renameProfile: noop,
    ...overrides,
  }
}

export function FakeProviders({
  session,
  profile,
  children,
}: {
  session?: Partial<SessionContextValue>
  profile?: Partial<ProfileContextValue>
  children: ReactNode
}) {
  return (
    <SessionContext value={fakeSessionValue(session)}>
      <ProfileContext value={fakeProfileValue(profile)}>{children}</ProfileContext>
    </SessionContext>
  )
}
