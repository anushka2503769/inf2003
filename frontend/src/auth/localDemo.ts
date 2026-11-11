import type { Session } from '@supabase/supabase-js'

/**
 * Local demo sign-in for the Docker quick start (backend/scripts/local_quickstart.sh).
 *
 * It exists so a marker can try the app without a Google, Supabase or Atlas account.
 * It is only reachable from `npm run dev:quickstart` (Vite dev server in "quickstart"
 * mode; see env.localDemoAuth), never from a production build. The token is unsigned:
 * the quick-start backend accepts it only because it runs with
 * AUTH_ALLOW_UNVERIFIED_TOKENS=true, which the backend refuses under APP_ENV=production.
 */

/** Must match demo_user_id in backend/scripts/local_quickstart.sh. */
export const DEMO_USER_ID = '7e57de30-0000-4000-8000-000000000001'
export const DEMO_EMAIL = 'demo.student@example.com'
export const DEMO_NAME = 'Demo Student'

const STORAGE_KEY = 'jobless-simulator.local-demo'
const ONE_DAY_SECONDS = 24 * 60 * 60

function base64Url(value: string): string {
  return btoa(value).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

/** A JWT-shaped token with the claims the backend reads (`sub`, `email`). Not signed. */
export function makeDemoToken(nowSeconds: number = Math.floor(Date.now() / 1000)): string {
  const header = { alg: 'HS256', typ: 'JWT' }
  const payload = {
    sub: DEMO_USER_ID,
    email: DEMO_EMAIL,
    aud: 'authenticated',
    role: 'authenticated',
    iat: nowSeconds,
    exp: nowSeconds + ONE_DAY_SECONDS,
    user_metadata: { full_name: DEMO_NAME },
  }
  // The third segment must still be valid base64url: PyJWT decodes it even when it
  // skips checking the signature. It is a marker, not a signature.
  return [header, payload, 'local-demo-unsigned']
    .map(part => base64Url(typeof part === 'string' ? part : JSON.stringify(part)))
    .join('.')
}

/** Just enough of a Supabase session for the app: the token and the user's identity. */
export function makeDemoSession(): Session {
  const now = Math.floor(Date.now() / 1000)
  return {
    access_token: makeDemoToken(now),
    refresh_token: '',
    token_type: 'bearer',
    expires_in: ONE_DAY_SECONDS,
    expires_at: now + ONE_DAY_SECONDS,
    user: {
      id: DEMO_USER_ID,
      email: DEMO_EMAIL,
      aud: 'authenticated',
      app_metadata: {},
      user_metadata: { full_name: DEMO_NAME },
      created_at: new Date(now * 1000).toISOString(),
    },
  } as Session
}

function storage(): Storage | null {
  try {
    return window.localStorage
  } catch {
    return null
  }
}

export function loadDemoSession(): Session | null {
  return storage()?.getItem(STORAGE_KEY) === 'signed-in' ? makeDemoSession() : null
}

export function rememberDemoSignIn(): void {
  storage()?.setItem(STORAGE_KEY, 'signed-in')
}

export function forgetDemoSignIn(): void {
  storage()?.removeItem(STORAGE_KEY)
}
