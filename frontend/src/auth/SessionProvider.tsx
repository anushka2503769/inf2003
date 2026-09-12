import { createContext, useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { Session } from '@supabase/supabase-js'

import { configureApiAuth } from '../lib/api-client'
import { isAuthConfigured } from '../lib/env'
import { authCallbackUrl, supabase } from '../lib/supabase'

/**
 * Owns the Supabase session. Nothing else in the app reads from Supabase.
 *
 * This is deliberately separate from the profile: a student can hold a valid
 * Google session while having no `users` row yet, and the router needs to tell
 * those two states apart to decide between onboarding and the app.
 */

export type SessionStatus = 'loading' | 'signed-in' | 'signed-out' | 'unconfigured'

/** What Google told us about the student, before they have confirmed anything. */
export interface GoogleIdentity {
  email: string | null
  /** Name from the Google account; the prefill for onboarding, not the truth. */
  suggestedName: string | null
  avatarUrl: string | null
}

export interface SessionContextValue {
  status: SessionStatus
  session: Session | null
  identity: GoogleIdentity | null
  signInWithGoogle: () => Promise<void>
  signOut: () => Promise<void>
}

export const SessionContext = createContext<SessionContextValue | null>(null)

function readIdentity(session: Session | null): GoogleIdentity | null {
  if (session === null) return null
  const meta = session.user.user_metadata as Record<string, unknown>
  const pick = (key: string): string | null => {
    const value = meta[key]
    return typeof value === 'string' && value.trim() !== '' ? value.trim() : null
  }
  return {
    email: session.user.email ?? null,
    suggestedName: pick('full_name') ?? pick('name'),
    avatarUrl: pick('avatar_url') ?? pick('picture'),
  }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [status, setStatus] = useState<SessionStatus>(
    isAuthConfigured ? 'loading' : 'unconfigured',
  )

  useEffect(() => {
    if (supabase === null) return

    let active = true

    // getSession resolves the stored session and, on the callback URL, the
    // freshly exchanged one. onAuthStateChange then keeps us current through
    // token refreshes and sign-out in another tab.
    void supabase.auth.getSession().then(({ data }) => {
      if (!active) return
      setSession(data.session)
      setStatus(data.session ? 'signed-in' : 'signed-out')
    })

    const { data: subscription } = supabase.auth.onAuthStateChange((_event, next) => {
      if (!active) return
      setSession(next)
      setStatus(next ? 'signed-in' : 'signed-out')
    })

    return () => {
      active = false
      subscription.subscription.unsubscribe()
    }
  }, [])

  const signInWithGoogle = useCallback(async () => {
    if (supabase === null) return
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: authCallbackUrl(),
        // Ask Google to show the chooser so a shared laptop does not silently
        // sign in as whoever used it last.
        queryParams: { prompt: 'select_account' },
      },
    })
    if (error) throw error
  }, [])

  const signOut = useCallback(async () => {
    if (supabase === null) return
    await supabase.auth.signOut()
    setSession(null)
    setStatus('signed-out')
  }, [])

  // Hand the API client a way to read the current access token. Supabase
  // refreshes an expiring token inside getSession, so every request carries a
  // valid one without the client knowing anything about auth.
  useEffect(() => {
    configureApiAuth({
      getAccessToken: async () => {
        if (supabase === null) return null
        const { data } = await supabase.auth.getSession()
        return data.session?.access_token ?? null
      },
      onUnauthenticated: () => {
        void supabase?.auth.signOut()
      },
    })
  }, [])

  const value = useMemo<SessionContextValue>(
    () => ({
      status,
      session,
      identity: readIdentity(session),
      signInWithGoogle,
      signOut,
    }),
    [status, session, signInWithGoogle, signOut],
  )

  return <SessionContext value={value}>{children}</SessionContext>
}
