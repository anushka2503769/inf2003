import { useState, type FormEvent } from 'react'

import { useProfile } from '../../auth/useProfile'
import { useSession } from '../../auth/useSession'
import { InlineError } from '../../components/Feedback'
import { TextField } from '../../components/TextField'
import { toDisplayMessage } from '../../lib/api-client'
import { FULL_NAME_MAX_LENGTH, normaliseFullName, validateFullName } from '../../lib/validation'
import type { OnboardingStepProps } from './types'

/**
 * First and currently only onboarding step.
 *
 * Google's name is a prefill, not a decision: students use nicknames, and the
 * name on a school Google account is often the full legal one. They confirm or
 * replace it, and that value becomes users.full_name.
 */
export function ConfirmNameStep({ onComplete }: OnboardingStepProps) {
  const { identity } = useSession()
  const { createProfile } = useProfile()

  const [name, setName] = useState(identity?.suggestedName ?? '')
  const [touched, setTouched] = useState(false)
  const [saving, setSaving] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

  const fieldError = touched ? validateFullName(name) : null

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setTouched(true)
    setFailure(null)

    const problem = validateFullName(name)
    if (problem !== null) return

    setSaving(true)
    try {
      await createProfile(normaliseFullName(name))
      onComplete()
    } catch (cause: unknown) {
      setFailure(toDisplayMessage(cause))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <h1 className="heading-1">
        {identity?.suggestedName ? `Welcome, ${firstWord(identity.suggestedName)}` : 'Welcome'}
      </h1>
      <hr className="rule rule--heavy" />
      <p className="lede">
        Set the name you want to go by. It appears on your profile and nowhere else — employers
        never see this app.
      </p>

      <form className="stack" onSubmit={event => void handleSubmit(event)} noValidate>
        <TextField
          label="Your name"
          value={name}
          onChange={value => {
            setName(value)
            if (failure !== null) setFailure(null)
          }}
          error={fieldError}
          hint={identity?.email ?? undefined}
          autoComplete="name"
          autoFocus
          disabled={saving}
          maxLength={FULL_NAME_MAX_LENGTH}
          placeholder="e.g. Ana Lim"
        />

        {failure ? <InlineError>{failure}</InlineError> : null}

        <div className="actions">
          <button type="submit" className="button button--primary" disabled={saving}>
            {saving ? 'Saving…' : 'Save and continue'}
          </button>
        </div>
      </form>
    </>
  )
}

function firstWord(value: string): string {
  return value.trim().split(' ')[0]
}
