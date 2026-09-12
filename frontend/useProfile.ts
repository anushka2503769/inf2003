import { useContext } from 'react'

import { ProfileContext, type ProfileContextValue } from './ProfileProvider'

/** Reads the student's profile row. Throws if used outside ProfileProvider. */
export function useProfile(): ProfileContextValue {
  const value = useContext(ProfileContext)
  if (value === null) {
    throw new Error('useProfile must be used inside <ProfileProvider>.')
  }
  return value
}
