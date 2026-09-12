/**
 * Reads the browser-visible configuration.
 *
 * Everything here is shipped to the browser. Only publishable values belong in
 * a VITE_ variable; Supabase secret keys and database credentials stay in
 * backend/.env (see the warning in the root README).
 */

function read(name: string): string {
  const value = import.meta.env[name]
  return typeof value === 'string' ? value.trim() : ''
}

const supabaseUrl = read('VITE_SUPABASE_URL')
const supabasePublishableKey = read('VITE_SUPABASE_PUBLISHABLE_KEY')

/**
 * True when both Supabase values are present. When false the app still runs and
 * the sign-in screen explains what to add, instead of throwing on a blank page.
 */
export const isAuthConfigured = supabaseUrl !== '' && supabasePublishableKey !== ''

export const env = {
  supabaseUrl,
  supabasePublishableKey,
  /** Relative by default so the Vite dev proxy handles /api (no CORS setup). */
  apiBaseUrl: read('VITE_API_BASE_URL') || '/api',
  isDev: import.meta.env.DEV,
} as const

/** Names of the variables the sign-in screen tells the developer to set. */
export const REQUIRED_AUTH_ENV = [
  'VITE_SUPABASE_URL',
  'VITE_SUPABASE_PUBLISHABLE_KEY',
] as const

export function missingAuthEnv(): string[] {
  const missing: string[] = []
  if (supabaseUrl === '') missing.push('VITE_SUPABASE_URL')
  if (supabasePublishableKey === '') missing.push('VITE_SUPABASE_PUBLISHABLE_KEY')
  return missing
}
