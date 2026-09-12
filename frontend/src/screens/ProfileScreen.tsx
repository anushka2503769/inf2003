import { useEffect, useState, type FormEvent } from 'react'

import { useProfile } from '../auth/useProfile'
import { useSession } from '../auth/useSession'
import { InlineError } from '../components/Feedback'
import { TextField } from '../components/TextField'
import { toDisplayMessage } from '../lib/api-client'
import { FULL_NAME_MAX_LENGTH, normaliseFullName, validateFullName } from '../lib/validation'

export function ProfileScreen() {
  const { identity, signOut } = useSession()
  const { profile } = useProfile()

  return (
    <div className="stack-lg">
      <section className="stack">
        <h1 className="heading-1">Profile</h1>
        <hr className="rule rule--heavy" />
        <div className="identity">
          <Avatar url={identity?.avatarUrl ?? null} name={profile?.full_name ?? ''} />
          <div>
            <p className="identity__name">{profile?.full_name}</p>
            <p className="note">{identity?.email ?? 'Signed in with Google'}</p>
          </div>
        </div>
      </section>

      <NameEditor />

      <section className="stack">
        <h2 className="heading-2">Resume and skills</h2>
        <hr className="rule" />
        <p className="prose">
          Once you add a resume, the skills found in it appear here for you to confirm or correct.
          Those confirmed skills are what Discover matches jobs against.
        </p>
        <p className="note">Not built yet.</p>
      </section>

      <section className="stack">
        <h2 className="heading-2">Account</h2>
        <hr className="rule" />
        <p className="prose">
          Signing out clears this session on this device. Your saved jobs stay on your account.
        </p>
        <div className="actions">
          <button type="button" className="button" onClick={() => void signOut()}>
            Sign out
          </button>
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
    <section className="stack">
      <h2 className="heading-2">Your name</h2>
      <hr className="rule" />
      <form className="stack" onSubmit={event => void handleSubmit(event)} noValidate>
        <TextField
          label="Name"
          value={name}
          onChange={value => {
            setTouched(true)
            setName(value)
            if (failure !== null) setFailure(null)
          }}
          error={fieldError}
          hint="Shown on your profile. You can change it whenever you like."
          autoComplete="name"
          disabled={saving}
          maxLength={FULL_NAME_MAX_LENGTH}
        />

        {failure ? <InlineError>{failure}</InlineError> : null}

        <div className="actions">
          <button
            type="submit"
            className="button button--primary"
            disabled={saving || !changed || fieldError !== null}
          >
            {saving ? 'Saving…' : 'Save changes'}
          </button>
          {changed && !saving ? (
            <button
              type="button"
              className="button button--quiet"
              onClick={() => {
                setName(saved)
                setTouched(false)
                setFailure(null)
              }}
            >
              Discard
            </button>
          ) : null}
          <span className={confirmed ? 'saved-mark saved-mark--on' : 'saved-mark'} role="status">
            {confirmed ? 'Saved' : ''}
          </span>
        </div>
      </form>
    </section>
  )
}

function Avatar({ url, name }: { url: string | null; name: string }) {
  if (url !== null) {
    return <img className="avatar" src={url} alt="" width={56} height={56} referrerPolicy="no-referrer" />
  }
  const initial = name.trim().charAt(0).toUpperCase()
  return (
    <span className="avatar avatar--letter" aria-hidden="true">
      {initial || '·'}
    </span>
  )
}
