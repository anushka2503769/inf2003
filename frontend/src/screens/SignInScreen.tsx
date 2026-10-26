import { useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { useSession } from '../auth/useSession'
import { Badge } from '../components/Badge'
import { Brand } from '../components/Brand'
import { Card } from '../components/Card'
import { GoogleButton } from '../components/GoogleButton'
import { InlineError } from '../components/Feedback'
import { Meter } from '../components/Meter'
import { missingAuthEnv } from '../lib/env'
import { HOME_ROUTE } from '../app/routes'

/** Router state the auth callback leaves when Google sign-in was cancelled. */
export interface SignInLocationState {
  from?: string
  authError?: 'cancelled'
}

export function SignInScreen() {
  const { status, signInWithGoogle } = useSession()
  const location = useLocation()
  const cancelled = (location.state as SignInLocationState | null)?.authError === 'cancelled'
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (status === 'signed-in') return <Navigate to={HOME_ROUTE} replace />

  async function handleSignIn() {
    setBusy(true)
    setError(null)
    try {
      await signInWithGoogle()
      // On success the browser leaves for Google, so `busy` stays true.
    } catch {
      setBusy(false)
      setError('Google sign-in could not start. Check your connection and try again.')
    }
  }

  return (
    <div className="signin">
      <main className="signin__left">
        <Brand className="signin__brand" />

        <div className="signin__pitch">
          <div className="signin__copy">
            <h1 className="t-display">Your internship hunt, minus the spreadsheet.</h1>
            <p className="t-body muted">
              <span className="only-desktop">
                Swipe through about 500 real Singapore internship postings, ranked by the skills
                you already have. Keep track of what you applied to, and see what employers keep
                asking for.
              </span>
              <span className="only-mobile">
                About 500 real Singapore internship postings, ranked by the skills you already
                have.
              </span>
            </p>
          </div>

          <div className="signin__action">
            {status === 'unconfigured' ? (
              <SetupNotice />
            ) : (
              <>
                {error ? (
                  <InlineError>
                    <strong>Google sign-in did not start.</strong> Check your connection and try
                    again.
                  </InlineError>
                ) : cancelled ? (
                  <InlineError>
                    <strong>Google sign-in was cancelled.</strong> Nothing was saved. Try again
                    when you are ready.
                  </InlineError>
                ) : null}
                <GoogleButton
                  onClick={() => void handleSignIn()}
                  busy={busy}
                  autoFocus={cancelled}
                />
                <p className="t-meta only-desktop">
                  Google is the only way in. We use it to know it is you, nothing else.
                </p>
              </>
            )}
          </div>
        </div>

        <p className="t-meta signin__tagline">Temporarily jobless. Permanently organised.</p>
      </main>

      <div className="signin__right">
        <ProductPreview />
      </div>
    </div>
  )
}

/** Decorative picture of what Discover looks like. Hidden from assistive tech. */
function ProductPreview() {
  return (
    <div className="signin-preview" aria-hidden="true">
      <Card className="signin-preview__lead">
        <span className="t-meta">
          Match rank 1 <span className="dot-sep">·</span> Posted 21 Oct 2026
        </span>
        <span className="t-title-sm">Data Analyst Intern</span>
        <span className="muted">DBS Bank · Singapore</span>
        <span className="signin-preview__badges">
          <Badge>Internship</Badge>
          <Badge>Hybrid</Badge>
        </span>
        <span className="signin-preview__match">
          <span className="signin-preview__match-title">You have 3 of 5 required skills</span>
          <Meter value={3} total={5} variant="compact" />
        </span>
      </Card>
      <Card className="signin-preview__row signin-preview__row--2">
        <span>
          <span className="signin-preview__row-title">UX Research Intern</span>
          <span className="t-meta">Grab · One-north</span>
        </span>
        <Meter value={2} total={4} />
      </Card>
      <Card className="signin-preview__row signin-preview__row--3">
        <span>
          <span className="signin-preview__row-title">Software Engineer Intern</span>
          <span className="t-meta">GovTech · Singapore</span>
        </span>
        <Meter value={1} total={6} />
      </Card>
    </div>
  )
}

/**
 * Shown when the Supabase variables are missing. A teammate who has just cloned
 * the repository sees exactly what to add rather than a button that does nothing.
 */
function SetupNotice() {
  const missing = missingAuthEnv()
  return (
    <section className="setup">
      <h2 className="setup__title">Sign-in is not configured on this machine</h2>
      <p className="muted">
        Copy <code>frontend/.env.example</code> to <code>frontend/.env.local</code> and fill in{' '}
        {missing.length === 1 ? 'this value' : 'these values'} from the team&rsquo;s Supabase
        project, then restart <code>npm run dev</code>.
      </p>
      <ul className="setup__list">
        {missing.map(name => (
          <li key={name}>
            <code>{name}</code>
          </li>
        ))}
      </ul>
    </section>
  )
}
