import { createClient, type SupabaseClient } from '@supabase/supabase-js'

import { env, isAuthConfigured } from './env'

/**
 * Supabase is used for authentication only. Database reads and writes go
 * through the FastAPI backend, which owns both PostgreSQL and MongoDB, so this
 * client should never be used to query tables directly from the browser.
 *
 * The client is null when the VITE_SUPABASE_* variables are unset. Callers use
 * `isAuthConfigured` (or `requireSupabase`) rather than assuming it exists, so
 * a teammate who has not created frontend/.env.local still gets a working app
 * with an explanatory sign-in screen.
 */
export const supabase: SupabaseClient | null = isAuthConfigured
  ? createClient(env.supabaseUrl, env.supabasePublishableKey, {
      auth: {
        // PKCE keeps the authorization code exchange safe for a browser app.
        flowType: 'pkce',
        // Supabase reads the ?code= parameter from the callback URL for us.
        detectSessionInUrl: true,
        persistSession: true,
        autoRefreshToken: true,
        storageKey: 'jobless-simulator.auth',
      },
    })
  : null

export function requireSupabase(): SupabaseClient {
  if (supabase === null) {
    throw new Error(
      'Supabase is not configured. Set VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY in frontend/.env.local.',
    )
  }
  return supabase
}

/** Where Google returns the student after consent. Must be allow-listed in Supabase. */
export function authCallbackUrl(): string {
  return `${window.location.origin}/auth/callback`
}
