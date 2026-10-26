import { useEffect, type ReactNode } from 'react'
import { Route, Routes } from 'react-router-dom'

import { AppShell } from '../app/AppShell'
import { RequireProfile } from '../app/guards'
import { routes } from '../app/routes'
import { FullPageSpinner } from '../components/Feedback'
import { DiscoverFeed } from '../features/discover/DiscoverFeed'
import { mockDiscoverClient } from '../features/discover/mocks'
import { AuthCallbackScreen } from '../screens/AuthCallbackScreen'
import { NotFoundScreen } from '../screens/NotFoundScreen'
import { OnboardingScreen } from '../screens/onboarding/OnboardingScreen'
import { SignInScreen } from '../screens/SignInScreen'
import type { PreviewScene } from './types'

const GROUP = 'B1 Foundation'

/** The shell around whatever `content` is, at the route the scene starts on. */
function InShell({ content, menuOpen = false }: { content: ReactNode; menuOpen?: boolean }) {
  return (
    <Routes>
      <Route element={<AppShell defaultMenuOpen={menuOpen} />}>
        <Route path="*" element={content} />
      </Route>
    </Routes>
  )
}

/** Submits the first form on mount, to show its validation state. */
function SubmitOnMount({ children }: { children: ReactNode }) {
  useEffect(() => {
    const timer = window.setTimeout(() => {
      document.querySelector<HTMLButtonElement>('form button[type="submit"]')?.click()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [])
  return <>{children}</>
}

const discover = <DiscoverFeed client={mockDiscoverClient} onProfileMissing={() => {}} />

export const b1Scenes: PreviewScene[] = [
  {
    id: 'app-shell',
    title: 'App shell (Discover, not yet redesigned)',
    group: GROUP,
    path: routes.discover,
    reference: 'app-shell-account-menu-open.png',
    element: <InShell content={discover} />,
  },
  {
    id: 'app-shell-menu-open',
    title: 'App shell, account menu open',
    group: GROUP,
    path: routes.discover,
    reference: 'app-shell-account-menu-open.png',
    element: <InShell content={discover} menuOpen />,
  },
  {
    id: 'sign-in',
    title: 'Sign-in, default',
    group: GROUP,
    path: routes.signIn,
    reference: 'sign-in-default.png',
    session: { status: 'signed-out', session: null, identity: null },
    element: <SignInScreen />,
  },
  {
    id: 'sign-in-cancelled',
    title: 'Sign-in, Google cancelled',
    group: GROUP,
    path: { pathname: routes.signIn, state: { authError: 'cancelled' } },
    reference: 'sign-in-cancelled.png',
    session: { status: 'signed-out', session: null, identity: null },
    element: <SignInScreen />,
  },
  {
    id: 'sign-in-unconfigured',
    title: 'Sign-in, Supabase not configured (developer machine)',
    group: GROUP,
    path: routes.signIn,
    session: { status: 'unconfigured', session: null, identity: null },
    element: <SignInScreen />,
  },
  {
    id: 'auth-callback',
    title: 'Auth callback, finishing sign-in',
    group: GROUP,
    path: routes.authCallback,
    session: { status: 'loading', session: null, identity: null },
    element: <AuthCallbackScreen />,
  },
  {
    id: 'onboarding',
    title: 'Onboarding, name step',
    group: GROUP,
    path: routes.welcome,
    reference: 'onboarding-name-step.png',
    profile: { status: 'missing', profile: null, onboardingComplete: false },
    element: <OnboardingScreen />,
  },
  {
    id: 'onboarding-error',
    title: 'Onboarding, name step with error',
    group: GROUP,
    path: routes.welcome,
    reference: 'onboarding-name-step-error.png',
    profile: { status: 'missing', profile: null, onboardingComplete: false },
    element: (
      <SubmitOnMount>
        <OnboardingScreen />
      </SubmitOnMount>
    ),
  },
  {
    id: 'not-found',
    title: '404',
    group: GROUP,
    path: '/vault/archive',
    reference: 'shared-404.png',
    element: <NotFoundScreen />,
  },
  {
    id: 'loading',
    title: 'Full-page loading',
    group: GROUP,
    path: routes.discover,
    reference: 'shared-loading.png',
    element: <FullPageSpinner label="Loading your profile" />,
  },
  {
    id: 'profile-failed',
    title: 'Profile failed to load (RequireProfile guard)',
    group: GROUP,
    path: routes.discover,
    reference: 'shared-profile-failed.png',
    profile: {
      status: 'error',
      profile: null,
      onboardingComplete: false,
      error:
        'We could not reach the server. Check your connection and try again. Your saved postings are safe.',
    },
    element: (
      <Routes>
        <Route element={<RequireProfile />}>
          <Route path="*" element={null} />
        </Route>
      </Routes>
    ),
  },
]
