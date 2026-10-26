import { useState, type FormEvent } from 'react'

import { useProfile } from '../../auth/useProfile'
import { useSession } from '../../auth/useSession'
import { Button } from '../../components/Button'
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
  const { identity, signOut } = useSession()
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
      <div className="onb__intro">
        <h1 className="t-title">What should we call you?</h1>
        <p className="t-body muted only-desktop">
          Just a name for now. Skills and your resume come next, on your profile.
        </p>
      </div>

      <form className="onb__form" onSubmit={event => void handleSubmit(event)} noValidate>
        <TextField
          label="Name"
          value={name}
          onChange={value => {
            setName(value)
            if (failure !== null) setFailure(null)
          }}
          error={fieldError}
          hint="How we greet you. You can change it later on your profile."
          autoComplete="name"
          autoFocus
          disabled={saving}
          maxLength={FULL_NAME_MAX_LENGTH}
          placeholder="Your name"
          size="lg"
        />

        {failure ? (
          <InlineError>
            <strong>Your name was not saved.</strong> {failure}
          </InlineError>
        ) : null}

        <div className="onb__actions">
          <Button type="submit" variant="primary" size="lg" iconRight="arrow-right" busy={saving}>
            {saving ? 'Saving' : 'Continue'}
          </Button>
          <Button variant="ghost" onClick={() => void signOut()} disabled={saving}>
            Sign out
          </Button>
        </div>
      </form>
    </>
  )
}
