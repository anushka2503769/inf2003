import type { ReactNode } from 'react'

import { Icon, type IconName } from './Icon'

export type BadgeTone = 'neutral' | 'accent' | 'gap' | 'danger' | 'info' | 'outline'

/** A short status or attribute label. Colour always comes with words. */
export function Badge({
  tone = 'neutral',
  icon,
  children,
}: {
  tone?: BadgeTone
  icon?: IconName
  children: ReactNode
}) {
  return (
    <span className={`badge badge--${tone}`}>
      {icon ? <Icon name={icon} /> : null}
      {children}
    </span>
  )
}

/** REQUIRED / PREFERRED micro-label next to a skill. */
export function RequirementLabel({ required }: { required: boolean }) {
  return <span className={required ? 'req' : 'req req--pref'}>{required ? 'Required' : 'Preferred'}</span>
}

/**
 * The ledger tick: filled green with a check when the student has the skill,
 * an empty box when not. Decorative; the list it sits in names the state.
 */
export function Tick({ on }: { on: boolean }) {
  return (
    <span className={on ? 'tick tick--on' : 'tick tick--off'} aria-hidden="true">
      {on ? <Icon name="check" /> : null}
    </span>
  )
}
