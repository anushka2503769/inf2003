import type { ReactNode } from 'react'

/**
 * Loading, empty and failure states. Screens reuse these so that "the server is
 * slow" and "the server said no" look the same everywhere in the app.
 */

export function FullPageSpinner({ label }: { label: string }) {
  return (
    <div className="fullpage">
      <p className="fullpage__text" role="status">
        <span className="pulse" aria-hidden="true" />
        {label}
      </p>
    </div>
  )
}

export function FullPageMessage({
  title,
  body,
  actionLabel,
  onAction,
}: {
  title: string
  body: string
  actionLabel?: string
  onAction?: () => void
}) {
  return (
    <div className="fullpage">
      <div className="fullpage__panel">
        <h1 className="heading-2">{title}</h1>
        <p className="prose">{body}</p>
        {actionLabel && onAction ? (
          <button type="button" className="button button--primary" onClick={onAction}>
            {actionLabel}
          </button>
        ) : null}
      </div>
    </div>
  )
}

/** A failure tied to a specific form or section, not to the whole page. */
export function InlineError({ children }: { children: ReactNode }) {
  return (
    <p className="inline-error" role="alert">
      {children}
    </p>
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
