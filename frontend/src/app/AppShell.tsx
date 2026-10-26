import { useEffect, useId, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'

import { useProfile } from '../auth/useProfile'
import { useSession } from '../auth/useSession'
import { Brand, BrandMark } from '../components/Brand'
import { Button } from '../components/Button'
import { Icon, type IconName } from '../components/Icon'
import { NAVIGATION, routes, type RoutePath } from './routes'
import './AppShell.css'

/**
 * The frame every signed-in screen renders inside.
 *
 * Screens supply only their own content; the navigation, the content column
 * and the skip link live here, so four people building four screens end up
 * with one consistent page. Desktop (>= 768px) gets the sidebar; mobile gets a
 * top bar and a bottom tab bar.
 */

const NAV_ICONS: Record<RoutePath, IconName> = {
  [routes.signIn]: 'sign-out',
  [routes.authCallback]: 'sign-out',
  [routes.welcome]: 'user-circle',
  [routes.discover]: 'compass',
  [routes.vault]: 'tray',
  [routes.skillGap]: 'chart-bar-horizontal',
  [routes.profile]: 'user-circle',
}

/**
 * Content column width per screen: Discover and Profile read as one 720px
 * column, Vault and Skill Gap are tables and get 960px.
 */
const WIDE_ROUTES: ReadonlyArray<string> = [routes.vault, routes.skillGap]

/** Must match the breakpoint in AppShell.css. */
const MOBILE_QUERY = '(max-width: 767.98px)'

function initialsOf(name: string | null | undefined): string {
  const words = (name ?? '').trim().split(/\s+/).filter(Boolean)
  if (words.length === 0) return '?'
  const first = words[0][0] ?? ''
  const last = words.length > 1 ? (words[words.length - 1][0] ?? '') : (words[0][1] ?? '')
  return (first + last).toUpperCase()
}

export function AppShell({ defaultMenuOpen = false }: { defaultMenuOpen?: boolean }) {
  const { profile } = useProfile()
  const { identity, signOut } = useSession()
  const location = useLocation()

  const name = profile?.full_name ?? identity?.suggestedName ?? ''
  const email = identity?.email ?? ''
  const initials = initialsOf(name)

  const current = NAVIGATION.find(item => location.pathname.startsWith(item.to))
  const wide = WIDE_ROUTES.some(path => location.pathname.startsWith(path))

  const [menuOpen, setMenuOpen] = useState(defaultMenuOpen)
  const [menuAnchor, setMenuAnchor] = useState<'sidebar' | 'topbar'>(() =>
    typeof window.matchMedia === 'function' && window.matchMedia(MOBILE_QUERY).matches
      ? 'topbar'
      : 'sidebar',
  )
  const menuId = useId()
  const menuRef = useRef<HTMLDivElement>(null)
  const sidebarToggleRef = useRef<HTMLButtonElement>(null)
  const topbarToggleRef = useRef<HTMLButtonElement>(null)

  // Close the account menu on navigation (state adjusted during render).
  const [menuPath, setMenuPath] = useState(location.pathname)
  if (menuPath !== location.pathname) {
    setMenuPath(location.pathname)
    setMenuOpen(false)
  }

  // Escape closes and returns focus; a click outside closes.
  useEffect(() => {
    if (!menuOpen) return
    function toggle() {
      return menuAnchor === 'sidebar' ? sidebarToggleRef.current : topbarToggleRef.current
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setMenuOpen(false)
        toggle()?.focus()
      }
    }
    function onPointerDown(event: PointerEvent) {
      const target = event.target as Node
      if (menuRef.current?.contains(target) || toggle()?.contains(target)) return
      setMenuOpen(false)
    }
    document.addEventListener('keydown', onKeyDown)
    document.addEventListener('pointerdown', onPointerDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.removeEventListener('pointerdown', onPointerDown)
    }
  }, [menuOpen, menuAnchor])

  function openFrom(anchor: 'sidebar' | 'topbar') {
    setMenuAnchor(anchor)
    setMenuOpen(open => (anchor === menuAnchor ? !open : true))
  }

  const accountMenu = menuOpen ? (
    <div
      ref={menuRef}
      id={menuId}
      className={`account-menu menu account-menu--${menuAnchor}`}
      aria-label="Account"
      role="group"
    >
      <div className="menu__head">
        <p className="t-meta">Signed in with Google as</p>
        <p className="account-menu__email">{email || name}</p>
      </div>
      <Link to={routes.profile} className="menu__item">
        <Icon name="user-circle" />
        Profile
      </Link>
      <hr className="menu__sep" />
      <button type="button" className="menu__item" onClick={() => void signOut()}>
        <Icon name="sign-out" />
        Sign out
      </button>
    </div>
  ) : null

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>

      <aside className="sidebar">
        <Brand to={routes.discover} className="sidebar__brand" />

        <nav className="nav" aria-label="Main">
          {NAVIGATION.map(item => (
            <NavLink key={item.to} to={item.to} className="nav__item">
              <Icon name={NAV_ICONS[item.to]} />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className={menuOpen && menuAnchor === 'sidebar' ? 'account is-open' : 'account'}>
          <button
            ref={sidebarToggleRef}
            type="button"
            className="account__toggle"
            aria-expanded={menuOpen && menuAnchor === 'sidebar'}
            aria-controls={menuId}
            onClick={() => openFrom('sidebar')}
          >
            <span className="shell-avatar" aria-hidden="true">
              {initials}
            </span>
            <span className="account__text">
              <span className="account__name">{name}</span>
              {email ? <span className="account__mail">{email}</span> : null}
            </span>
          </button>
          <Button
            variant="ghost"
            iconOnly
            icon="sign-out"
            aria-label="Sign out"
            title="Sign out"
            onClick={() => void signOut()}
          />
        </div>
        {menuAnchor === 'sidebar' ? accountMenu : null}
      </aside>

      <header className="topbar">
        <BrandMark />
        <span className="topbar__title">{current?.label ?? 'Jobless Simulator'}</span>
        <button
          ref={topbarToggleRef}
          type="button"
          className="topbar__account"
          aria-label={`Account: ${name}`}
          aria-expanded={menuOpen && menuAnchor === 'topbar'}
          aria-controls={menuId}
          onClick={() => openFrom('topbar')}
        >
          <span className="shell-avatar shell-avatar--sm" aria-hidden="true">
            {initials}
          </span>
        </button>
        {menuAnchor === 'topbar' ? accountMenu : null}
      </header>

      <main id="main" className="shell__main" tabIndex={-1}>
        <div className={wide ? 'shell__column shell__column--wide' : 'shell__column'}>
          <Outlet />
        </div>
      </main>

      <nav className="tabbar" aria-label="Main">
        {NAVIGATION.map(item => (
          <NavLink key={item.to} to={item.to} className="tabbar__item">
            <Icon name={NAV_ICONS[item.to]} />
            {item.label}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
