import { useEffect } from 'react'
import { MemoryRouter } from 'react-router-dom'

import { FakeProviders } from './fakes'
import { SCENES } from './registry'
import './preview.css'

/**
 * Dev-only preview harness (never in `npm run build`: main.tsx imports it
 * lazily behind import.meta.env.DEV).
 *
 *   /__preview              index of every scene
 *   /__preview/<scene-id>   one scene, full viewport, fake session + mock data
 *   ?theme=dark             renders the scene with the dark tokens
 *
 * Marker for the build check: JOBLESS_PREVIEW_HARNESS
 */
export const PREVIEW_HARNESS_MARKER = 'JOBLESS_PREVIEW_HARNESS'

export default function PreviewApp() {
  const id = window.location.pathname.replace(/^\/__preview\/?/, '').replace(/\/$/, '')
  const theme = new URLSearchParams(window.location.search).get('theme')

  useEffect(() => {
    if (theme === 'dark') document.documentElement.dataset.theme = 'dark'
    else delete document.documentElement.dataset.theme
  }, [theme])

  if (id === '') return <PreviewIndex />

  const scene = SCENES.find(candidate => candidate.id === id)
  if (!scene) {
    return (
      <main className="preview-index">
        <h1 className="t-title">No scene called “{id}”.</h1>
        <p className="t-body muted">
          <a href="/__preview">Back to the index</a>
        </p>
      </main>
    )
  }

  return (
    <FakeProviders session={scene.session} profile={scene.profile}>
      <MemoryRouter initialEntries={[scene.path ?? '/']}>{scene.element}</MemoryRouter>
    </FakeProviders>
  )
}

function PreviewIndex() {
  const groups = [...new Set(SCENES.map(scene => scene.group))]
  return (
    <main className="preview-index" data-harness={PREVIEW_HARNESS_MARKER}>
      <header className="preview-index__head">
        <h1 className="t-title">Preview harness</h1>
        <p className="t-body muted">
          Every redesigned screen and state with a fake session and mock data. Dev server only.
          Add <code>?theme=dark</code> to any scene for the dark tokens.
        </p>
      </header>
      {groups.map(group => (
        <section key={group} className="preview-index__group">
          <h2 className="t-label">{group}</h2>
          <ul className="preview-index__list">
            {SCENES.filter(scene => scene.group === group).map(scene => (
              <li key={scene.id} className="preview-index__item">
                <a href={`/__preview/${scene.id}`}>{scene.title}</a>
                <span className="t-meta">
                  {scene.id}
                  {scene.reference ? ` · matches ${scene.reference}` : ''}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </main>
  )
}
