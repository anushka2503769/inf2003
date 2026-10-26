/**
 * Segmented meter: one cell per item, so "3 of 5" is countable at a glance and
 * never needs a percentage. `steps` is the thin ink variant used for onboarding
 * progress; `compact` draws fixed 16px cells (small previews, list rows).
 */
export function Meter({
  value,
  total,
  label,
  variant = 'default',
}: {
  value: number
  total: number
  /** Accessible name; defaults to "<value> of <total>". */
  label?: string
  variant?: 'default' | 'steps' | 'compact'
}) {
  const filled = Math.max(0, Math.min(value, total))
  const classes = ['meter', variant !== 'default' ? `meter--${variant}` : ''].filter(Boolean).join(' ')
  return (
    <div className={classes} role="img" aria-label={label ?? `${filled} of ${total}`}>
      {Array.from({ length: total }, (_, index) => (
        <span key={index} className={index < filled ? 'meter__cell is-on' : 'meter__cell'} />
      ))}
    </div>
  )
}
