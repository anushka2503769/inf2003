import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { AppShell } from './app/AppShell'
import { RequireNoProfile, RequireProfile, RequireSession } from './app/guards'
import { routes } from './app/routes'
import { ProfileProvider } from './auth/ProfileProvider'
import { SessionProvider } from './auth/SessionProvider'
import { AuthCallbackScreen } from './screens/AuthCallbackScreen'
import { NotFoundScreen } from './screens/NotFoundScreen'
import { DiscoverScreen, SkillGapScreen, VaultScreen } from './screens/Placeholders'
import { OnboardingScreen } from './screens/onboarding/OnboardingScreen'
import { ProfileScreen } from './screens/ProfileScreen'
import { SignInScreen } from './screens/SignInScreen'

/**
 * Route table for the whole app.
 *
 * The nesting is the access rule: everything under RequireSession needs a
 * Google session, and everything under RequireProfile additionally needs a
 * finished onboarding. New feature screens go inside the AppShell branch.
 */
export default function App() {
  return (
    <BrowserRouter>
      <SessionProvider>
        <ProfileProvider>
          <Routes>
            <Route path={routes.signIn} element={<SignInScreen />} />
            <Route path={routes.authCallback} element={<AuthCallbackScreen />} />

            <Route element={<RequireSession />}>
              <Route element={<RequireNoProfile />}>
                <Route path={routes.welcome} element={<OnboardingScreen />} />
              </Route>

              <Route element={<RequireProfile />}>
                <Route element={<AppShell />}>
                  <Route path={routes.discover} element={<DiscoverScreen />} />
                  <Route path={routes.vault} element={<VaultScreen />} />
                  <Route path={routes.skillGap} element={<SkillGapScreen />} />
                  <Route path={routes.profile} element={<ProfileScreen />} />
                </Route>
              </Route>
            </Route>

            <Route path="/" element={<Navigate to={routes.discover} replace />} />
            <Route path="*" element={<NotFoundScreen />} />
          </Routes>
        </ProfileProvider>
      </SessionProvider>
    </BrowserRouter>
  )
}
