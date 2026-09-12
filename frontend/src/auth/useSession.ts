import { useContext } from 'react'

import { SessionContext, type SessionContextValue } from './SessionProvider'

/** Reads the Supabase session. Throws if used outside SessionProvider. */
export function useSession(): SessionContextValue {
  const value = useContext(SessionContext)
  if (value === null) {
    throw new Error('useSession must be used inside <SessionProvider>.')
  }
  return value
}
