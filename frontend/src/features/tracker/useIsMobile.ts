import { useEffect, useState } from 'react'

/** Must match the shell breakpoint (AppShell.tsx / AppShell.css). */
export const MOBILE_QUERY = '(max-width: 767.98px)'

function matches(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    && window.matchMedia(MOBILE_QUERY).matches
}

/**
 * True below the 768px breakpoint. Vault uses it to expose exactly one status
 * switcher to assistive tech: the tabs on desktop, the "Show" dropdown on
 * mobile. Without matchMedia (jsdom) it reports desktop.
 */
export function useIsMobile(): boolean {
  const [mobile, setMobile] = useState(matches)
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const query = window.matchMedia(MOBILE_QUERY)
    const onChange = () => setMobile(query.matches)
    onChange()
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])
  return mobile
}
