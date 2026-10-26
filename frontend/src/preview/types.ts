import type { ReactNode } from 'react'
import type { InitialEntry } from 'react-router-dom'

import type { ProfileContextValue } from '../auth/ProfileProvider'
import type { SessionContextValue } from '../auth/SessionProvider'

/**
 * One screen or state in the preview harness, reachable at /__preview/<id>.
 *
 * `element` renders inside a MemoryRouter that starts at `path`, wrapped in
 * fake session and profile providers. Use <Routes> inside `element` when the
 * screen needs route params or the app shell's <Outlet>.
 */
export interface PreviewScene {
  /** URL slug; also the screenshot file name (e.g. "sign-in-cancelled"). */
  id: string
  /** Human label on the index page. */
  title: string
  /** Groups scenes on the index page, e.g. "B1 Foundation". */
  group: string
  /** Initial router entry (path, or { pathname, state }). Defaults to "/". */
  path?: InitialEntry
  /** Name of the matching reference PNG in the design hand-off, if any. */
  reference?: string
  session?: Partial<SessionContextValue>
  profile?: Partial<ProfileContextValue>
  element: ReactNode
}
