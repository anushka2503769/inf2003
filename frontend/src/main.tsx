import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './style.css'

// Dev-only preview harness at /__preview (see docs/design/README.md). In a
// production build import.meta.env.DEV is false, so the lazy import is dead
// code and the harness never reaches dist/.
const PreviewApp = import.meta.env.DEV ? lazy(() => import('./preview/PreviewApp')) : null
const showPreview = PreviewApp !== null && window.location.pathname.startsWith('/__preview')

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {showPreview && PreviewApp ? (
      <Suspense fallback={null}>
        <PreviewApp />
      </Suspense>
    ) : (
      <App />
    )}
  </StrictMode>,
)
