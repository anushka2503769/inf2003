import { ICON_PATHS, type IconName } from './iconPaths'

export type { IconName }

/**
 * A Phosphor glyph drawn in currentColor. Icons are decorative by default
 * (aria-hidden); the control around them carries the accessible name.
 */
export function Icon({
  name,
  size,
  className,
}: {
  name: IconName
  size?: 'sm' | 'lg' | 'kbd'
  className?: string
}) {
  const classes = ['icon', size ? `icon--${size}` : '', className ?? ''].filter(Boolean).join(' ')
  return (
    <svg
      className={classes}
      viewBox="0 0 256 256"
      fill="currentColor"
      aria-hidden="true"
      focusable="false"
    >
      <path d={ICON_PATHS[name]} />
    </svg>
  )
}
