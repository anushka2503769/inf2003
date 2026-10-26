import { Link } from 'react-router-dom'

import { Icon } from './Icon'

/** The ledger-tick mark on its own (sidebar, mobile top bar). */
export function BrandMark() {
  return (
    <span className="mark" aria-hidden="true">
      <Icon name="check" />
    </span>
  )
}

/** Mark plus wordmark. Pass `to` to make it a home link. */
export function Brand({ to, className }: { to?: string; className?: string }) {
  const classes = ['brand', className ?? ''].filter(Boolean).join(' ')
  if (to) {
    return (
      <Link to={to} className={classes}>
        <BrandMark />
        Jobless Simulator
      </Link>
    )
  }
  return (
    <span className={classes}>
      <BrandMark />
      Jobless Simulator
    </span>
  )
}
