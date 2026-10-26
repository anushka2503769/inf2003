import type { CSSProperties, HTMLAttributes, ReactNode } from 'react'

/** A bordered surface with the large radius. `padded` adds 32px inside. */
export function Card({
  as: Tag = 'div',
  padded = false,
  raised = false,
  className,
  children,
  ...rest
}: {
  as?: 'div' | 'article' | 'section' | 'li'
  padded?: boolean
  raised?: boolean
  className?: string
  children: ReactNode
} & HTMLAttributes<HTMLElement>) {
  const classes = ['card', padded ? 'card--pad' : '', raised ? 'card--raised' : '', className ?? '']
    .filter(Boolean)
    .join(' ')
  return (
    <Tag className={classes} {...rest}>
      {children}
    </Tag>
  )
}

/**
 * A list row with a hairline underneath. Set the grid with `columns`
 * (any grid-template-columns value), e.g. "1fr 170px 112px 196px" for Vault.
 */
export function Row({
  as: Tag = 'div',
  columns,
  interactive = false,
  tone,
  className,
  children,
  ...rest
}: {
  as?: 'div' | 'li'
  columns?: string
  interactive?: boolean
  tone?: 'confirm'
  className?: string
  children: ReactNode
} & HTMLAttributes<HTMLElement>) {
  const classes = [
    'row',
    interactive ? 'row--interactive' : '',
    tone === 'confirm' ? 'row--confirm' : '',
    className ?? '',
  ]
    .filter(Boolean)
    .join(' ')
  const style = columns ? ({ '--row-columns': columns } as CSSProperties) : undefined
  return (
    <Tag className={classes} style={style} {...rest}>
      {children}
    </Tag>
  )
}
