import { useId, type ChangeEvent } from 'react'

import { Icon, type IconName } from './Icon'

/**
 * The app's text input: a label above, a boxed field, and one line of help or
 * correction underneath. Errors are announced (role="alert") and linked to the
 * input with aria-describedby.
 */
export function TextField({
  label,
  value,
  onChange,
  hint,
  error,
  autoComplete,
  autoFocus,
  disabled,
  maxLength,
  placeholder,
  size = 'md',
  icon,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  hint?: string
  error?: string | null
  autoComplete?: string
  autoFocus?: boolean
  disabled?: boolean
  maxLength?: number
  placeholder?: string
  /** 'lg' is the 44px field used on entry screens and on mobile. */
  size?: 'md' | 'lg'
  /** Leading glyph inside the field, e.g. "magnifying-glass" for search. */
  icon?: IconName
}) {
  const id = useId()
  const messageId = `${id}-message`
  const message = error ?? hint

  const inputClass = [
    'field__input',
    size === 'lg' ? 'field__input--lg' : '',
    error ? 'field__input--invalid' : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      <div className="field__control">
        {icon ? <Icon name={icon} /> : null}
        <input
          id={id}
          className={inputClass}
          type="text"
          value={value}
          onChange={(event: ChangeEvent<HTMLInputElement>) => onChange(event.target.value)}
          aria-invalid={error ? true : undefined}
          aria-describedby={message ? messageId : undefined}
          autoComplete={autoComplete}
          autoFocus={autoFocus}
          disabled={disabled}
          maxLength={maxLength}
          placeholder={placeholder}
          spellCheck={false}
        />
      </div>
      {message ? (
        <p
          id={messageId}
          className={error ? 'field__message field__message--error' : 'field__message'}
          role={error ? 'alert' : undefined}
        >
          {error ? <Icon name="warning-circle" /> : null}
          <span>{message}</span>
        </p>
      ) : null}
    </div>
  )
}
