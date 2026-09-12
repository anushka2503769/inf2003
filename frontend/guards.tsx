import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { useProfile } from '../auth/useProfile'
import { useSession } from '../auth/useSession'
import { FullPageMessage, FullPageSpinner } from '../components/Feedback'
import { HOME_ROUTE, routes } from './routes'

/**
 * Two gates, applied in order.
 *
 * RequireSession answers "do we know who this is?" and RequireProfile answers
 * "have they finished onboarding?". Keeping them separate means a half-finished
 * sign-up lands on onboarding rather than bouncing back to the sign-in screen.
 */

export function RequireSession() {
  const { status } = useSession()
  const location = useLocation()

  if (status === 'loading') return <FullPageSpinner label="Checking your session" />

  if (status !== 'signed-in') {
    // Remember where they were headed so the sign-in returns them there.
    return <Navigate to={routes.signIn} replace state={{ from: location.pathname }} />
  }

  return <Outlet />
}

export function RequireProfile() {
  const { status, onboardingComplete, error, reload } = useProfile()

  if (status === 'idle' || status === 'loading') {
    return <FullPageSpinner label="Loading your profile" />
  }

  if (status === 'missing') return <Navigate to={routes.welcome} replace />

  // A row can exist while onboarding is unfinished, once there are steps after
  // the name. The backend owns that rule and we follow it.
  if (status === 'ready' && !onboardingComplete) {
    return <Navigate to={routes.welcome} replace />
  }

  if (status === 'error') {
    return (
      <FullPageMessage
        title="Your profile did not load"
        body={error ?? 'The server did not answer.'}
        actionLabel="Try again"
        onAction={reload}
      />
    )
  }

  return <Outlet />
}

/**
 * Keeps an already-onboarded student out of the welcome flow, while still
 * letting someone with a half-finished onboarding back in to finish it.
 */
export function RequireNoProfile() {
  const { status, onboardingComplete } = useProfile()

  if (status === 'idle' || status === 'loading') {
    return <FullPageSpinner label="Loading your profile" />
  }
  if (status === 'ready' && onboardingComplete) return <Navigate to={HOME_ROUTE} replace />

  return <Outlet />
}
