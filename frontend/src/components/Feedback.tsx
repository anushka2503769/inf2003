import type { ReactNode } from 'react'

import { Button } from './Button'
import { Icon, type IconName } from './Icon'

/**
 * Loading, empty and failure states. Screens reuse these so that "the server is
 * slow" and "the server said no" look the same everywhere in the app.
 */

/** A spinner on its own; pass `label` when nothing else names the wait. */
export function Spinner({ size, label }: { size?: 'sm'; label?: string }) {
  return (
    <span
      className={size === 'sm' ? 'spinner spinner--sm' : 'spinner'}
      role={label ? 'status' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    />
  )
}

export function FullPageSpinner({ label }: { label: string }) {
  return (
    <div className="center-page center-page--status">
      <div className="center-page__status" role="status">
        <Spinner />
        <p className="muted">{label}…</p>
      </div>
    </div>
  )
}

/**
 * Empty or explanatory state: a glyph, a serif title, one line of body and up
 * to two actions. `center` is used on full pages; inline it reads left-aligned.
 */
export function EmptyState({
  icon,
  eyebrow,
  title,
  titleAs: Title = 'h2',
  children,
  actions,
  center = false,
  flush = false,
}: {
  icon: IconName
  /** Small line above the glyph, e.g. "404". */
  eyebrow?: ReactNode
  title: string
  titleAs?: 'h1' | 'h2' | 'h3'
  children?: ReactNode
  actions?: ReactNode
  center?: boolean
  /** Drop the default vertical padding (when a card already pads it). */
  flush?: boolean
}) {
  const classes = ['empty', center ? 'empty--center' : '', flush ? 'empty--flush' : '']
    .filter(Boolean)
    .join(' ')
  return (
    <div className={classes}>
      {eyebrow ? <p className="empty__eyebrow mono">{eyebrow}</p> : null}
      <span className="empty__glyph" aria-hidden="true">
        <Icon name={icon} />
      </span>
      <Title className="empty__title">{title}</Title>
      {children ? <p className="empty__body">{children}</p> : null}
      {actions ? <div className="empty__actions">{actions}</div> : null}
    </div>
  )
}

export function FullPageMessage({
  title,
  body,
  actionLabel,
  onAction,
  actionIcon = 'arrow-clockwise',
  actionIconRight,
  secondaryLabel,
  onSecondary,
  icon = 'warning-circle',
  eyebrow,
}: {
  title: string
  body: ReactNode
  actionLabel?: string
  onAction?: () => void
  /** Leading icon on the primary action; pass null for none. */
  actionIcon?: IconName | null
  /** Trailing icon on the primary action (e.g. "arrow-right" for navigation). */
  actionIconRight?: IconName
  secondaryLabel?: string
  onSecondary?: () => void
  icon?: IconName
  eyebrow?: ReactNode
}) {
  const primary =
    actionLabel && onAction ? (
      <Button
        variant="primary"
        icon={actionIconRight ? undefined : (actionIcon ?? undefined)}
        iconRight={actionIconRight}
        onClick={onAction}
      >
        {actionLabel}
      </Button>
    ) : null
  const secondary =
    secondaryLabel && onSecondary ? (
      <Button variant="ghost" onClick={onSecondary}>
        {secondaryLabel}
      </Button>
    ) : null

  return (
    <main className="center-page center-page--status">
      <EmptyState
        icon={icon}
        eyebrow={eyebrow}
        title={title}
        titleAs="h1"
        center
        flush
        actions={primary || secondary ? <>{primary}{secondary}</> : undefined}
      >
        {body}
      </EmptyState>
    </main>
  )
}

/**
 * A failure tied to a specific form or section, not to the whole page. Lead
 * with what happened in <strong>, then what it means.
 */
export function InlineError({
  children,
  actionLabel,
  onAction,
}: {
  children: ReactNode
  /** Optional recovery action, e.g. "Retry". */
  actionLabel?: string
  onAction?: () => void
}) {
  return (
    <div className="inline-error" role="alert">
      <Icon name="warning-circle" />
      <span className="inline-error__text">{children}</span>
      {actionLabel && onAction ? (
        <Button variant="secondary" icon="arrow-clockwise" onClick={onAction}>
          {actionLabel}
        </Button>
      ) : null}
    </div>
  )
}

/** A non-blocking caution ("gap") or explanation ("info"). */
export function Notice({
  tone = 'gap',
  children,
}: {
  tone?: 'gap' | 'info'
  children: ReactNode
}) {
  return (
    <div className={`notice notice--${tone}`}>
      <Icon name={tone === 'info' ? 'info' : 'warning-circle'} />
      <div className="notice__text">{children}</div>
    </div>
  )
}

/**
 * Marks a section the other pair owns. Says plainly that it is not built, so a
 * reviewer never mistakes an empty screen for a broken one.
 */
export function NotBuiltYet({ title, body }: { title: string; body: string }) {
  return (
    <section className="stack">
      <h1 className="heading-1">{title}</h1>
      <hr className="rule" />
      <p className="prose">{body}</p>
      <p className="note">
        This screen is a placeholder from the frontend shell. The feature work lands here.
      </p>
    </section>
  )
}
