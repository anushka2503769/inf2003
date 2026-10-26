import type { ReactNode } from 'react'

import { Icon } from './Icon'

/**
 * A skill chip. With `onRemove` it gets a remove control whose accessible
 * name is "Remove <label>"; without it, it is a static label.
 */
export function Chip({
  label,
  onRemove,
  disabled,
  children,
}: {
  label: string
  onRemove?: () => void
  disabled?: boolean
  children?: ReactNode
}) {
  return (
    <span className={onRemove ? 'chip' : 'chip chip--static'}>
      {children ?? label}
      {onRemove ? (
        <button
          type="button"
          className="chip__x"
          onClick={onRemove}
          disabled={disabled}
          aria-label={`Remove ${label}`}
        >
          <Icon name="x" />
        </button>
      ) : null}
    </span>
  )
}

export function ChipList({ children, label }: { children: ReactNode; label?: string }) {
  return (
    <div className="chips" role={label ? 'group' : undefined} aria-label={label}>
      {children}
    </div>
  )
}
