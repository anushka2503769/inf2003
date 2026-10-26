import { useRef, type KeyboardEvent } from 'react'

export interface TabItem<T extends string> {
  id: T
  label: string
  /** Optional count shown in the small pill. */
  count?: number
}

/**
 * Underlined tabs (WAI-ARIA tabs pattern): one tab in the tab order, arrow
 * keys move between them. The caller renders the panel with
 * id={`${idPrefix}-panel`} and aria-labelledby={`${idPrefix}-${active}`}.
 */
export function Tabs<T extends string>({
  items,
  active,
  onChange,
  label,
  idPrefix,
}: {
  items: ReadonlyArray<TabItem<T>>
  active: T
  onChange: (id: T) => void
  label: string
  idPrefix: string
}) {
  const refs = useRef<Array<HTMLButtonElement | null>>([])

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next = -1
    if (event.key === 'ArrowRight') next = (index + 1) % items.length
    else if (event.key === 'ArrowLeft') next = (index - 1 + items.length) % items.length
    else if (event.key === 'Home') next = 0
    else if (event.key === 'End') next = items.length - 1
    if (next < 0) return
    event.preventDefault()
    refs.current[next]?.focus()
    onChange(items[next].id)
  }

  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {items.map((item, index) => {
        const selected = item.id === active
        return (
          <button
            key={item.id}
            ref={element => {
              refs.current[index] = element
            }}
            type="button"
            role="tab"
            id={`${idPrefix}-${item.id}`}
            aria-selected={selected}
            aria-controls={`${idPrefix}-panel`}
            tabIndex={selected ? 0 : -1}
            className="tab"
            onClick={() => onChange(item.id)}
            onKeyDown={event => handleKeyDown(event, index)}
          >
            {item.label}
            {item.count !== undefined ? <span className="tab__count">{item.count}</span> : null}
          </button>
        )
      })}
    </div>
  )
}
