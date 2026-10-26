import { useCallback, useEffect, useState, type FormEvent } from 'react'

import { useProfile } from '../auth/useProfile'
import { useSession } from '../auth/useSession'
import { Button } from '../components/Button'
import { InlineError } from '../components/Feedback'
import { TextField } from '../components/TextField'
import { loadProfile, profileSkillsClient, resumeClient as defaultResumeClient, type ResumeClient } from '../features/resume/client'
import { ResumeSection } from '../features/resume/ResumeSection'
import type { SkillsClient } from '../features/skills/client'
import '../features/skills/profile-screen.css'
import { toDisplayMessage } from '../lib/api-client'
import type { MeResponse, UserSkill } from '../types/api'
import { FULL_NAME_MAX_LENGTH, normaliseFullName, validateFullName } from '../lib/validation'

export interface ProfileScreenProps {
  /** Overrides for tests and the design preview; the app uses the data-source defaults. */
  resumeClient?: ResumeClient
  skillsClient?: SkillsClient
  load?: () => Promise<MeResponse>
}

export function ProfileScreen({
  resumeClient = defaultResumeClient,
  skillsClient = profileSkillsClient,
  load = loadProfile,
}: ProfileScreenProps = {}) {
  const { identity, signOut } = useSession()

  return (
    <div className="profile">
      <header className="profile__head">
        <h1 className="profile__title">Profile</h1>
        <p className="profile__lede">Your name, resume, skills and account.</p>
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
        <ResumeAndSkills client={resumeClient} skillsClient={skillsClient} load={load} />
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

/**
 * Loads the confirmed skills for the section below. The skills come from the
 * same GET /api/me the app shell uses; this screen keeps its own copy so a
 * confirm can refresh them without reloading the whole shell.
 */
function ResumeAndSkills({
  client,
  skillsClient,
  load,
}: {
  client: ResumeClient
  skillsClient: SkillsClient
  load: () => Promise<MeResponse>
}) {
  const [skills, setSkills] = useState<UserSkill[] | null>(null)
  const [failure, setFailure] = useState<string | null>(null)

  const reload = useCallback(async () => {
    const result = await load()
    setSkills(result.skills)
  }, [load])

  const firstLoad = useCallback(async () => {
    setFailure(null)
    try {
      await reload()
    } catch (cause: unknown) {
      setFailure(toDisplayMessage(cause))
    }
  }, [reload])

  useEffect(() => {
    void firstLoad()
  }, [firstLoad])

  if (failure !== null) {
    return (
      <InlineError actionLabel="Retry" onAction={() => void firstLoad()}>
        {failure}
      </InlineError>
    )
  }
  if (skills === null) {
    return (
      <p className="muted" role="status">
        Loading your skills…
      </p>
    )
  }
  return (
    <ResumeSection confirmedSkills={skills} onProfileReload={reload} client={client} skillsClient={skillsClient} />
  )
}
