import { render, screen } from '@testing-library/react'
import { createRef } from 'react'
import { describe, expect, it } from 'vitest'

import { Button } from './Button'

describe('Button', () => {
  it('forwards a ref to the DOM button so callers can focus it', () => {
    const ref = createRef<HTMLButtonElement>()
    render(<Button ref={ref}>Save</Button>)
    const button = screen.getByRole('button', { name: 'Save' })
    expect(ref.current).toBe(button)
    ref.current?.focus()
    expect(button).toHaveFocus()
  })
})
