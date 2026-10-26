import { useEffect, useState } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'

import { useSession } from '../auth/useSession'
import { FullPageMessage, FullPageSpinner } from '../components/Feedback'
import { HOME_ROUTE, routes } from '../app/routes'
import type { SignInLocationState } from './SignInScreen'

/**
 * Where Google returns the student.
 *
 * The Supabase client exchanges the authorization code for a session as soon as
 * it loads, so this screen only has to wait for that to land, surface a denial
 * from Google, and then get out of the way. A cancel at the Google screen goes
 * straight back to sign-in, which explains it inline.
 */
export function AuthCallbackScreen() {
  const { status } = useSession()
  const [params] = useSearchParams()
  const [tooSlow, setTooSlow] = useState(false)

  const providerError = params.get('error_description') ?? params.get('error')
  // Prefer the error code; fall back to the description only when no code was sent.
  const errorCode = params.get('error')
  const cancelled = errorCode === 'access_denied' || (errorCode === null && providerError === 'access_denied')

  useEffect(() => {
    // If the exchange has not completed in a few seconds, something is wrong
    // with the redirect URL configuration rather than with the network.
    const timer = window.setTimeout(() => setTooSlow(true), 8000)
    return () => window.clearTimeout(timer)
  }, [])

  if (cancelled) {
    const state: SignInLocationState = { authError: 'cancelled' }
    return <Navigate to={routes.signIn} replace state={state} />
  }

  if (providerError !== null) {
    return (
      <FullPageMessage
        title="Google did not complete the sign-in."
        body={providerError}
        actionLabel="Back to sign-in"
        actionIcon="arrow-left"
        onAction={() => window.location.assign(routes.signIn)}
      />
    )
  }

  if (status === 'signed-in') return <Navigate to={HOME_ROUTE} replace />
  if (status === 'signed-out' && tooSlow) {
    return (
      <FullPageMessage
        title="The sign-in did not finish."
        body="Google returned without a session. Confirm that this address is listed as a redirect URL in the Supabase project, then try again."
        actionLabel="Back to sign-in"
        actionIcon="arrow-left"
        onAction={() => window.location.assign(routes.signIn)}
      />
    )
  }

  return <FullPageSpinner label="Finishing your sign-in" />
}
