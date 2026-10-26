// Screenshots every scene of the dev-only preview harness at desktop and mobile.
//
//   cd frontend && npx vite --port 5199 --strictPort &      # any free port
//   PLAYWRIGHT=/path/to/node_modules/playwright \
//     node ../docs/design/shoot-preview.mjs http://127.0.0.1:5199 ./shots [scene-id ...]
//
// PLAYWRIGHT points at a Playwright install (the repo does not depend on it).
// Output: <out>/<scene>--desktop.png (1440x900) and <out>/<scene>--mobile.png (390x844).
import { createRequire } from 'node:module'
import { mkdirSync } from 'node:fs'
import path from 'node:path'

const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright')

const [base = 'http://127.0.0.1:5199', out = 'preview-shots', ...only] = process.argv.slice(2)
const sizes = { desktop: { width: 1440, height: 900 }, mobile: { width: 390, height: 844 } }

mkdirSync(out, { recursive: true })
const browser = await chromium.launch({ args: ['--single-process', '--no-sandbox', '--disable-gpu'] })
try {
  // One page for everything: --single-process Chromium dies when a page closes.
  const page = await browser.newPage({ viewport: sizes.desktop, deviceScaleFactor: 1 })
  await page.goto(`${base}/__preview`)
  await page.waitForSelector('.preview-index__item a')
  const ids = await page.$$eval('.preview-index__item a', links =>
    links.map(link => new URL(link.href).pathname.replace('/__preview/', '')),
  )

  for (const id of ids.filter(candidate => only.length === 0 || only.includes(candidate))) {
    for (const [name, viewport] of Object.entries(sizes)) {
      await page.setViewportSize(viewport)
      await page.goto(`${base}/__preview/${id}`)
      await page.evaluate(() => document.fonts.ready)
      await page.waitForTimeout(500) // lazy chunk + mock clients (~90ms)
      const file = path.join(out, `${id}--${name}.png`)
      await page.screenshot({ path: file })
      console.log(file)
    }
  }
} finally {
  await browser.close()
}
