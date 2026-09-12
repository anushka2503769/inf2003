import { useId, type ChangeEvent } from 'react'

/**
 * The app's one input treatment: a label, a value written on a rule, and a
 * single line of help or correction underneath.
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
}) {
  const id = useId()
  const messageId = `${id}-message`
  const message = error ?? hint

  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      <input
        id={id}
        className={error ? 'field__input field__input--invalid' : 'field__input'}
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
      {message ? (
        <p
          id={messageId}
          className={error ? 'field__message field__message--error' : 'field__message'}
          role={error ? 'alert' : undefined}
        >
          {message}
        </p>
      ) : null}
    </div>
  )
}
