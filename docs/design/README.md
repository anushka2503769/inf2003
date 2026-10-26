# Design: UI v1 "The Notebook"

Approved design (Figma): <https://www.figma.com/design/wahBUi8w3scqzkMs765Pmv>

Warm greys, one ledger-green accent, Newsreader (serif) for page titles, Instrument Sans for
everything you operate, IBM Plex Mono only inside key hints. Sidebar on desktop, bottom tab bar
on mobile (breakpoint 768px). The redesign lands in four PRs: B1 Foundation (this), then B2
Discover, B3 Vault and B4 Skill Gap + Profile, which build on B1's tokens and components.

`reference/` holds the hand-off screenshots for the B1 screens. Desktop references are
1440x924 because the hand-off adds a 24px label strip on top; compare against a 1440x900
viewport.

## Where things live

| Design piece | File |
|---|---|
| Tokens (colour, type, spacing, radius, elevation, layout; light + `[data-theme="dark"]`) | `frontend/src/styles/tokens.css` |
| Self-hosted fonts + `@font-face` (`font-display: swap`) | `frontend/src/styles/fonts.css`, `frontend/src/assets/fonts/*.woff2`, licence `frontend/src/assets/fonts/OFL.txt` |
| Reset, type roles (`.t-display`, `.t-title`, `.t-meta`, `.t-label`...), focus ring, skip link | `frontend/src/styles/base.css` |
| Component classes (`.btn`, `.field__input`, `.badge`, `.chip`, `.tabs`, `.meter`, `.card`, `.row`, `.inline-error`, `.notice`, `.empty`, `.menu`, `.spinner`, `.skel`) | `frontend/src/styles/components.css` |
| Sign-in, onboarding, full-page states | `frontend/src/styles/entry.css` |
| Entry point + compatibility layer (old class and token names, restyled) | `frontend/src/style.css` |
| App shell (sidebar, mobile top bar, tab bar, account menu) | `frontend/src/app/AppShell.tsx`, `AppShell.css` |
| Icons (Phosphor, MIT) | `frontend/src/components/Icon.tsx`, `iconPaths.ts`, licence `frontend/src/assets/icons/LICENSE.md` |

React components in `frontend/src/components/`:

| Component | Use |
|---|---|
| `Button`, `buttonClass()`, `Kbd` | `variant` primary / secondary / ghost / danger / accent, `size` md (36px) / lg (44px), `icon`, `iconRight`, `kbd`, `busy`. `buttonClass()` gives a `<Link>` or `<a>` the same look. |
| `TextField`, `Select` | Label above, boxed field, one help or error line (error has `role="alert"`). `size="lg"` for entry screens. |
| `Badge`, `RequirementLabel`, `Tick` | Status labels; REQUIRED / PREFERRED; the ledger tick. |
| `Chip`, `ChipList` | Skill chips; the remove button is named "Remove <skill>". |
| `Meter` | Segmented meter, one cell per item (`variant` default / steps / compact). |
| `Card`, `Row` | Bordered surface; list row with `columns` for the grid. |
| `Tabs` | WAI-ARIA tabs with arrow-key movement and count pills. |
| `InlineError`, `Notice`, `EmptyState`, `Spinner`, `FullPageSpinner`, `FullPageMessage` | Feedback and empty states (`Feedback.tsx`). |
| `Brand`, `BrandMark`, `GoogleButton` | Wordmark, the mark alone, the Google sign-in button. |

Rules for B2-B4:

- Read colours, type and spacing from the tokens. `grep -nE "#[0-9a-fA-F]{3,8}"` over your CSS
  should find nothing outside `tokens.css`.
- Screens not yet redesigned still use `.button`, `.heading-1`, `.stack`, `.rule`, `--ink`,
  `--rule` and friends; `style.css` maps them onto the new look. When your screen no longer uses
  one, delete it from the compatibility layer.
- The shell picks the content column: 720px for Discover and Profile, 960px for Vault and
  Skill Gap (`WIDE_ROUTES` in `AppShell.tsx`). Screens render only their content.
- Every interactive element gets the global focus ring (2px accent outline); do not remove it.
  On mobile, `.btn`, fields, tabs and menu items grow to the 44px touch minimum.

## Preview harness (dev only)

`/__preview` on the dev server renders every redesigned screen and state with a fake session,
fake profile and mock data clients, so screens behind sign-in can be checked and screenshotted
without Supabase. `main.tsx` imports it lazily behind `import.meta.env.DEV`, so it is not in
`npm run build` output (check: `grep -r JOBLESS_PREVIEW_HARNESS frontend/dist` finds nothing).

```bash
cd frontend
npx vite --port 5199 --strictPort      # any free port
# open http://127.0.0.1:5199/__preview  (add ?theme=dark to any scene)
```

Scenes live in `frontend/src/preview/`. To add yours (B2-B4), create `scenes-b2.tsx` exporting a
`PreviewScene[]` (see `types.ts` and `scenes-b1.tsx`), then spread it into `SCENES` in
`registry.ts`. Pass mock clients as props (for example
`<DiscoverFeed client={mockDiscoverClient} />`) rather than relying on `VITE_DATA=mock`.

## Screenshots

`docs/design/shoot-preview.mjs` screenshots every scene at 1440x900 and 390x844. The repo does not
depend on Playwright; point `PLAYWRIGHT` at any install:

```bash
cd frontend
PLAYWRIGHT=/path/to/node_modules/playwright \
  node ../docs/design/shoot-preview.mjs http://127.0.0.1:5199 ./preview-shots [scene-id ...]
```

Files are named `<scene>--desktop.png` and `<scene>--mobile.png`. Each scene's `reference` field
names the hand-off PNG it should match.
