# Google sign-in, onboarding and profile — files to add

Every path below is relative to the repository root, so copying the two folders
in this archive over your clone puts each file where it belongs.

## How to apply

```
git checkout -b feat/auth-shell
# copy backend/ and frontend/ from this archive over the repo root
cd frontend && npm ci
cd ../backend && uv sync --locked
```

## New files

frontend/
  .env.example                          Template for the browser-visible config
  src/types/api.ts                      Shared API types (source of truth)
  src/lib/api-client.ts                 The only place that calls fetch
  src/lib/api.ts                        Typed endpoint helpers
  src/lib/env.ts                        Typed environment access
  src/lib/supabase.ts                   Supabase client, auth only
  src/lib/validation.ts                 Name rules, mirrored on the backend
  src/vite-env.d.ts                     Typing for the VITE_ variables
  src/app/routes.ts                     Every path in the app
  src/app/guards.tsx                    Session and onboarding gates
  src/app/AppShell.tsx                  Navigation rail and content column
  src/auth/SessionProvider.tsx          Owns the Supabase session
  src/auth/ProfileProvider.tsx          Owns the SQL users row
  src/auth/useSession.ts                Session hook
  src/auth/useProfile.ts                Profile hook
  src/components/Feedback.tsx           Loading, empty and failure states
  src/components/TextField.tsx          The one input treatment
  src/components/GoogleButton.tsx       Google sign-in control
  src/screens/SignInScreen.tsx          Sign-in, plus an unconfigured state
  src/screens/AuthCallbackScreen.tsx    Where Google returns the student
  src/screens/ProfileScreen.tsx         Profile and name editing
  src/screens/NotFoundScreen.tsx        404
  src/screens/Placeholders.tsx          Discover, Vault, Skill gap stubs
  src/screens/onboarding/               Onboarding sequence and the name step

backend/
  app/config.py                         Settings from the environment
  app/errors.py                         The { error: { code, message } } envelope
  app/auth.py                           Supabase token verification
  app/schemas.py                        Profile models and name rules
  app/store.py                          ProfileStore seam for the database work
  app/routers/profile.py                GET, POST and PATCH /api/me
  tests/test_profile.py                 Onboarding, editing, isolation
  tests/test_auth.py                    Token verification

## Modified files

frontend/package.json                   Adds supabase-js, react-router-dom, plugin-react
frontend/package-lock.json              Regenerated to match
frontend/vite.config.ts                 Adds the React plugin
frontend/index.html                     Fonts and description
frontend/src/App.tsx                    Replaced with the route table
frontend/src/style.css                  Replaced with the design system
backend/pyproject.toml                  Adds pyjwt[crypto]
backend/uv.lock                         Regenerated to match
backend/app/main.py                     Registers error handlers and the router
backend/.env.example                    Documents the new auth variables

The existing /api/health route and its test are unchanged.

## Before it runs

Copy frontend/.env.example to frontend/.env.local and fill in the Supabase
project URL and publishable key. Without them the app still starts and the
sign-in screen explains what is missing.

On the backend, set SUPABASE_URL in backend/.env so the API can fetch the
project's public keys and verify tokens.

AUTH_ALLOW_UNVERIFIED_TOKENS=true lets the API accept unsigned tokens for local
testing before the Supabase project exists. It must never appear on a deployed
instance; the app refuses to start with it set alongside APP_ENV=production.

## Checks

```
cd frontend && npm run build
cd ../backend && uv run --locked ruff check . && uv run --locked ruff format --check . && uv run --locked pytest
```
