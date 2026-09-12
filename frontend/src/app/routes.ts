/**
 * Every path in the app. Import from here instead of writing string literals,
 * so a rename is one edit and a typo is a type error.
 */
export const routes = {
  signIn: '/sign-in',
  authCallback: '/auth/callback',
  welcome: '/welcome',
  discover: '/discover',
  vault: '/vault',
  skillGap: '/skill-gap',
  profile: '/profile',
} as const

export type RoutePath = (typeof routes)[keyof typeof routes]

/** Where a signed-in, onboarded student lands. */
export const HOME_ROUTE: RoutePath = routes.discover

/** The primary navigation, in order, for the rail and the mobile bar. */
export const NAVIGATION: ReadonlyArray<{ to: RoutePath; label: string }> = [
  { to: routes.discover, label: 'Discover' },
  { to: routes.vault, label: 'Vault' },
  { to: routes.skillGap, label: 'Skill gap' },
  { to: routes.profile, label: 'Profile' },
]
