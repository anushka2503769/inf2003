import { useEffect, useState, type FormEvent } from 'react'

import { useProfile } from '../auth/useProfile'
import { useSession } from '../auth/useSession'
import { Button } from '../components/Button'
import { InlineError } from '../components/Feedback'
import { Icon } from '../components/Icon'
import { TextField } from '../components/TextField'
import '../features/skills/profile-screen.css'
import { toDisplayMessage } from '../lib/api-client'
import { FULL_NAME_MAX_LENGTH, normaliseFullName, validateFullName } from '../lib/validation'

export function ProfileScreen() {
  const { identity, signOut } = useSession()

  return (
    <div className="profile">
      <header className="page-head">
        <h1 className="page-head__title">Profile</h1>
        <p className="page-head__lede">Your name and account. Your resume and skills will live here too.</p>
      </header>

      <NameEditor />

      <section className="profile__section" aria-labelledby="profile-resume-heading">
        <div className="profile__section-head">
          <h2 className="profile__heading" id="profile-resume-heading">Resume and skills</h2>
          <p className="profile__desc">
            Once you add a resume, the skills found in it appear here for you to confirm or correct.
            Those confirmed skills are what Discover matches jobs against.
          </p>
        </div>
        <div className="profile__placeholder">
          <Icon name="file-text" size="lg" />
          <p>
            <strong>Not built yet.</strong>{' '}
            <span className="muted">Resume upload and skill confirmation arrive in a later update.</span>
          </p>
        </div>
      </section>

      <section className="profile__section" aria-labelledby="profile-account-heading">
        <div className="profile__section-head">
          <h2 className="profile__heading" id="profile-account-heading">Account</h2>
          <p className="profile__desc">
            Signed in with Google{identity?.email ? <> as <strong>{identity.email}</strong></> : null}.
            Signing out clears this session on this device. Your saved jobs stay on your account.
          </p>
        </div>
        <div className="actions">
          <Button icon="sign-out" onClick={() => void signOut()}>
            Sign out
          </Button>
        </div>
      </section>
    </div>
  )
}

/**
 * Name editing. The form starts from the saved value, enables its action only
 * when the value has actually changed, and confirms with the same word the
 * button used.
 */
function NameEditor() {
  const { profile, renameProfile } = useProfile()
  const saved = profile?.full_name ?? ''

  const [name, setName] = useState(saved)
  const [touched, setTouched] = useState(false)
  const [saving, setSaving] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const [confirmed, setConfirmed] = useState(false)

  // Follow the stored value if it changes elsewhere, unless the student is
  // partway through typing a different one.
  useEffect(() => {
    if (!touched) setName(saved)
  }, [saved, touched])

  useEffect(() => {
    if (!confirmed) return
    const timer = window.setTimeout(() => setConfirmed(false), 2600)
    return () => window.clearTimeout(timer)
  }, [confirmed])

  const fieldError = touched ? validateFullName(name) : null
  const changed = normaliseFullName(name) !== saved

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setFailure(null)
    if (validateFullName(name) !== null) {
      setTouched(true)
      return
    }
    if (!changed) return

    setSaving(true)
    try {
      await renameProfile(normaliseFullName(name))
      setTouched(false)
      setConfirmed(true)
    } catch (cause: unknown) {
      setFailure(toDisplayMessage(cause))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="profile__section" aria-labelledby="profile-name-heading">
      <div className="profile__section-head">
        <h2 className="profile__heading" id="profile-name-heading">Name</h2>
      </div>
      <form className="profile__name-form" onSubmit={event => void handleSubmit(event)} noValidate>
        <div className="profile__name-row">
          <TextField
            label="Display name"
            value={name}
            onChange={value => {
              setTouched(true)
              setName(value)
              if (failure !== null) setFailure(null)
            }}
            error={fieldError}
            autoComplete="name"
            disabled={saving}
            maxLength={FULL_NAME_MAX_LENGTH}
          />

          <div className="actions profile__name-actions">
            <Button
              type="submit"
              variant="primary"
              busy={saving}
              disabled={!changed || fieldError !== null}
            >
              {saving ? 'Saving…' : 'Save name'}
            </Button>
            {changed && !saving ? (
              <Button
                variant="ghost"
                onClick={() => {
                  setName(saved)
                  setTouched(false)
                  setFailure(null)
                }}
              >
                Discard
              </Button>
            ) : null}
            <span className={confirmed ? 'saved-mark saved-mark--on' : 'saved-mark'} role="status">
              {confirmed ? 'Saved' : ''}
            </span>
          </div>
        </div>

        {failure ? <InlineError>{failure}</InlineError> : null}
      </form>
    </section>
  )
}
