import type { ButtonHTMLAttributes, ReactNode } from 'react'

import { Icon, type IconName } from './Icon'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'accent'

export interface ButtonLookProps {
  variant?: ButtonVariant
  size?: 'md' | 'lg'
  block?: boolean
  /** Square icon-only button; pass `aria-label`. */
  iconOnly?: boolean
}

/**
 * Class list for the button look, for elements that are not <button>
 * (a router <Link>, an <a href> to a posting).
 */
export function buttonClass({
  variant = 'secondary',
  size = 'md',
  block = false,
  iconOnly = false,
}: ButtonLookProps = {}, extra?: string): string {
  return [
    'btn',
    `btn--${variant}`,
    size === 'lg' ? 'btn--lg' : '',
    block ? 'btn--block' : '',
    iconOnly ? 'btn--icon' : '',
    extra ?? '',
  ]
    .filter(Boolean)
    .join(' ')
}

/** A key hint inside a button, e.g. the arrow keys on Discover. */
export function Kbd({ children, label }: { children: ReactNode; label?: string }) {
  if (children === '←' || children === '→') {
    return (
      <kbd className="kbd" aria-label={label ?? (children === '←' ? 'Left arrow key' : 'Right arrow key')}>
        <Icon name={children === '←' ? 'arrow-left' : 'arrow-right'} size="kbd" />
      </kbd>
    )
  }
  return (
    <kbd className="kbd" aria-label={label}>
      {children}
    </kbd>
  )
}

/**
 * The app's button. Defaults to type="button" so it never submits a form by
 * accident; pass type="submit" for the form's primary action.
 */
export function Button({
  variant,
  size,
  block,
  iconOnly,
  icon,
  iconRight,
  kbd,
  kbdLeft,
  busy,
  className,
  children,
  type = 'button',
  disabled,
  ...rest
}: ButtonLookProps &
  Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> & {
    icon?: IconName
    iconRight?: IconName
    /** Key hint after the label (e.g. "→"). */
    kbd?: string
    /** Key hint before the label (e.g. "←"). */
    kbdLeft?: string
    /** Shows a small spinner and disables the button. */
    busy?: boolean
    children?: ReactNode
  }) {
  return (
    <button
      type={type}
      className={buttonClass({ variant, size, block, iconOnly }, className)}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      {...rest}
    >
      {kbdLeft ? <Kbd>{kbdLeft}</Kbd> : null}
      {busy ? <span className="spinner spinner--sm" aria-hidden="true" /> : icon ? <Icon name={icon} /> : null}
      {children}
      {iconRight && !busy ? <Icon name={iconRight} /> : null}
      {kbd ? <Kbd>{kbd}</Kbd> : null}
    </button>
  )
}
