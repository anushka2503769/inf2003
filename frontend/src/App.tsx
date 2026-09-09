import { useEffect, useState } from 'react'

export default function App() {
  const [status, setStatus] = useState('Checking connection…')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 5000)
    let active = true
    setStatus('Checking connection…')

    async function checkConnection() {
      try {
        const response = await fetch('/api/health', { signal: controller.signal })
        if (!response.ok) throw new Error('API unavailable')
        const data: unknown = await response.json()
        if (typeof data !== 'object' || data === null || !('status' in data) || data.status !== 'ok') {
          throw new Error('Unexpected API response')
        }
        if (active) setStatus('Backend connected')
      } catch {
        if (active) setStatus('Backend unavailable. Start the API on port 8000, then retry.')
      } finally {
        window.clearTimeout(timeout)
      }
    }

    void checkConnection()
    return () => {
      active = false
      controller.abort()
      window.clearTimeout(timeout)
    }
  }, [attempt])

  return (
    <main>
      <p className="eyebrow">INF2003 · Team workspace</p>
      <h1>Jobless Simulator</h1>
      <p className="intro">Find opportunities that fit your skills. Understand what to learn next.</p>
      <section aria-labelledby="setup-title">
        <h2 id="setup-title">Development starter</h2>
        <p>This is the shared project foundation. The application features are still to be built.</p>
        <p role="status">{status}</p>
        <button onClick={() => setAttempt(value => value + 1)}>Check connection</button>
      </section>
      <section aria-labelledby="scope-title">
        <h2 id="scope-title">MVP areas</h2>
        <ul>
          <li><strong>Profile:</strong> upload a resume and confirm skills.</li>
          <li><strong>Discover:</strong> filter and review matched opportunities.</li>
          <li><strong>Vault:</strong> keep decisions and track applications.</li>
          <li><strong>Skill gap:</strong> compare your skills with a target role.</li>
        </ul>
      </section>
    </main>
  )
}
