import { NavLink, Outlet } from 'react-router-dom'

import { useProfile } from '../auth/useProfile'
import { NAVIGATION, routes } from './routes'

/**
 * The frame every signed-in screen renders inside.
 *
 * Screens supply only their own content; the rail, the content column width
 * and the skip link live here, so four people building four screens end up
 * with one consistent page.
 */
export function AppShell() {
  const { profile } = useProfile()

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>

      <header className="rail">
        <NavLink to={routes.discover} className="wordmark wordmark--small">
          Jobless
          <br />
          Simulator
        </NavLink>

        <nav className="rail__nav" aria-label="Main">
          {NAVIGATION.map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => (isActive ? 'rail__link rail__link--active' : 'rail__link')}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <p className="rail__identity">{profile?.full_name}</p>
      </header>

      <main id="main" className="content">
        <div className="column">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
