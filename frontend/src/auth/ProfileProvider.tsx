import { createContext, useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import { profileApi } from '../lib/api'
import { isApiError } from '../lib/api-client'
import type { Profile } from '../types/api'
import { useSession } from './useSession'

/**
 * Owns the student's row in the SQL `users` table.
 *
 * `missing` is a normal state, not an error: it means Google sign-in succeeded
 * but onboarding has not run yet. Treating a 404 as failure here would send a
 * first-time student to an error screen instead of to onboarding.
 */

export type ProfileStatus = 'idle' | 'loading' | 'ready' | 'missing' | 'error'

export interface ProfileContextValue {
  status: ProfileStatus
  profile: Profile | null
  onboardingComplete: boolean
  error: string | null
  reload: () => Promise<void>
  /** Creates the row during onboarding. */
  createProfile: (fullName: string) => Promise<void>
  /** Renames the student. Resolves once the server has confirmed. */
  renameProfile: (fullName: string) => Promise<void>
}

export const ProfileContext = createContext<ProfileContextValue | null>(null)

export function ProfileProvider({ children }: { children: ReactNode }) {
  const { status: sessionStatus } = useSession()
  const [profile, setProfile] = useState<Profile | null>(null)
  const [onboardingComplete, setOnboardingComplete] = useState(false)
  const [status, setStatus] = useState<ProfileStatus>('idle')
  const [error, setError] = useState<string | null>(null)

  // Pulled out of the effect so an explicit reload() call can await the same
  // fetch the effect runs on session change, and reject on genuine failure —
  // "missing" (no profile row yet) is deliberately NOT a rejection, since
  // that is a normal state here, not an error.
  const fetchProfile = useCallback(async (signal?: AbortSignal) => {
    setStatus('loading')
    setError(null)
    try {
      const result = await profileApi.get(signal)
      if (signal?.aborted) return
      setProfile(result.profile)
      setOnboardingComplete(result.onboarding_complete)
      setStatus('ready')
    } catch (cause) {
      if (signal?.aborted) return
      if (isApiError(cause) && cause.code === 'not_found') {
        setProfile(null)
        setOnboardingComplete(false)
        setStatus('missing')
        return
      }
      setStatus('error')
      setError(
        isApiError(cause) && cause.code === 'network_error'
          ? 'Cannot reach the server. Start the API on port 8000, then reload.'
          : 'Your profile did not load.',
      )
      // Re-thrown so an explicit reload() caller (e.g. SkillEditor, after an
      // add/remove) can tell success from failure. The session-change effect
      // below ignores this rejection on purpose — it already reflects the
      // failure via `status`/`error` state, which is all that effect needs.
      throw cause
    }
  }, [])

  useEffect(() => {
    if (sessionStatus !== 'signed-in') {
      // Clear immediately on sign-out so one student's name can never be shown
      // inside another student's session on a shared machine.
      setProfile(null)
      setOnboardingComplete(false)
      setStatus('idle')
      setError(null)
      return
    }

    const controller = new AbortController()
    fetchProfile(controller.signal).catch(() => {
      // Intentionally swallowed: fetchProfile has already set status/error;
      // this catch exists only so a genuine failure doesn't surface as an
      // unhandled promise rejection from this effect.
    })

    return () => controller.abort()
  }, [sessionStatus, fetchProfile])

  const reload = useCallback(() => fetchProfile(), [fetchProfile])

  const createProfile = useCallback(async (fullName: string) => {
    const result = await profileApi.create({ full_name: fullName })
    setProfile(result.profile)
    setOnboardingComplete(result.onboarding_complete)
    setStatus('ready')
    setError(null)
  }, [])

  const renameProfile = useCallback(async (fullName: string) => {
    const updated = await profileApi.update({ full_name: fullName })
    setProfile(updated)
    setStatus('ready')
  }, [])

  const value = useMemo<ProfileContextValue>(
    () => ({ status, profile, onboardingComplete, error, reload, createProfile, renameProfile }),
    [status, profile, onboardingComplete, error, reload, createProfile, renameProfile],
  )

  return <ProfileContext value={value}>{children}</ProfileContext>
}