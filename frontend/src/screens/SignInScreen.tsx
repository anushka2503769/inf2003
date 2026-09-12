import { useState } from 'react'
import { Navigate } from 'react-router-dom'

import { useSession } from '../auth/useSession'
import { GoogleButton } from '../components/GoogleButton'
import { InlineError } from '../components/Feedback'
import { missingAuthEnv } from '../lib/env'
import { HOME_ROUTE } from '../app/routes'

export function SignInScreen() {
  const { status, signInWithGoogle } = useSession()
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
    <div className="entry">
      <div className="entry__panel">
        <h1 className="wordmark">
          Jobless
          <br />
          Simulator
        </h1>
        <hr className="rule rule--heavy" />

        <p className="lede">
          Find internships that match the skills you actually have, and see what you are missing
          for the role you want next.
        </p>

        {status === 'unconfigured' ? <SetupNotice /> : null}

        {status !== 'unconfigured' ? (
          <>
            <div className="entry__action">
              <GoogleButton onClick={() => void handleSignIn()} busy={busy} />
            </div>
            {error ? <InlineError>{error}</InlineError> : null}
            <p className="note">
              Signing in with your school Google account keeps your saved jobs and your skills
              separate from everyone else&rsquo;s. Nothing is posted to your account.
            </p>
          </>
        ) : null}
      </div>
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
      <h2 className="heading-3">Sign-in is not configured on this machine</h2>
      <p className="prose">
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
