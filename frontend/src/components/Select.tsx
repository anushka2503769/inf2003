import { useId, type ChangeEvent } from 'react'

export interface SelectOption {
  value: string
  label: string
}

/**
 * A labelled native <select> drawn like the hand-off's select. Native keeps
 * keyboard, screen-reader and mobile pickers working with no extra code.
 * An empty-string option renders as the placeholder ("Any type").
 */
export function Select({
  label,
  value,
  onChange,
  options,
  placeholder,
  size = 'md',
  hint,
  disabled,
  hideLabel = false,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  options: ReadonlyArray<SelectOption>
  /** Label of the empty-value option; omit to have no empty option. */
  placeholder?: string
  size?: 'md' | 'lg'
  hint?: string
  disabled?: boolean
  /** Keep the label for screen readers only (compact toolbars). */
  hideLabel?: boolean
}) {
  const id = useId()
  const hintId = `${id}-hint`
  const classes = ['field__input', size === 'lg' ? 'field__input--lg' : ''].filter(Boolean).join(' ')
  return (
    <div className="field">
      <label className={hideLabel ? 'sr-only' : 'field__label'} htmlFor={id}>
        {label}
      </label>
      <select
        id={id}
        className={classes}
        value={value}
        disabled={disabled}
        aria-describedby={hint ? hintId : undefined}
        onChange={(event: ChangeEvent<HTMLSelectElement>) => onChange(event.target.value)}
      >
        {placeholder !== undefined ? <option value="">{placeholder}</option> : null}
        {options.map(option => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {hint ? (
        <p id={hintId} className="field__message">
          {hint}
        </p>
      ) : null}
    </div>
  )
}
