# Jobless Simulator

INF2003 team project: discover relevant internships/jobs, save decisions, track
applications and identify skill gaps for a target role.

**Current state:** minimal development foundation. The frontend connects to a Python
health endpoint. Product features and database integrations are not implemented yet.

## Team

| Members | Responsibility |
|---|---|
| Zhihao | Moderator, final reviewer, integration and consolidation |
| Nasya and Anuska | Frontend (`frontend/`) |
| Jason and Jiaxin | Backend and future database integration (`backend/`) |

## First-time setup

Install Git, Node.js **22.12+ within the 22.x line** (use `.nvmrc` with nvm), and
[uv](https://docs.astral.sh/uv/getting-started/installation/). uv installs the
Python **3.14** runtime selected in `backend/.python-version` if needed.
Run these commands from the repository root after cloning:

```sh
cd frontend
npm ci
cd ../backend
uv sync --locked
```

Windows users can run the same commands in PowerShell. A virtual-environment activation
step is not necessary: `uv run` uses `backend/.venv` automatically. The first install
requires internet access. Do not use global pip installs for this project.

## Environment configuration

The current health-check skeleton does not require environment variables. When database
integration begins, create a private backend configuration from the committed template:

```sh
cp backend/.env.example backend/.env
```

Windows PowerShell users can run `Copy-Item backend/.env.example backend/.env` instead.
Replace the placeholders only in `backend/.env`; Git ignores that file. Supabase secret
keys and MongoDB credentials stay on the backend and must never use a `VITE_` prefix,
because Vite exposes prefixed values to the browser. Job API and LLM variables will be
added after the team selects those providers.

## Start development

Open two terminals, each starting in the repository root.

Frontend:

```sh
cd frontend
npm run dev
```

Backend:

```sh
cd backend
uv run --locked uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Frontend: http://127.0.0.1:5173
- API health: http://127.0.0.1:8000/api/health
- Interactive API documentation: http://127.0.0.1:8000/docs
- OpenAPI schema: http://127.0.0.1:8000/openapi.json

The Vite development server forwards `/api` requests to the backend on port 8000.
Use relative `/api/...` paths in frontend requests. This avoids development CORS
configuration. No credentials, `.env` file or database service is needed for this starter.
If the frontend reports that the backend is unavailable, start the API and click
**Check connection**. If a port is occupied, stop the other process; changing the API
port also requires changing the Vite proxy target.

The Vite proxy is development-only. `npm run preview` previews static build output;
it does not provide a backend proxy. Deployment routing will be configured when a
hosting platform is selected.

## Checks before a pull request

Frontend:

```sh
cd frontend
npm run build
```

This runs strict TypeScript checking and builds the app. No frontend test runner or
separate frontend lint framework is installed yet; add behavioural tests with the
first product interaction.

Backend:

```sh
cd backend
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest
```

GitHub Actions runs these checks for pull requests once this workflow is pushed.
It does not run against production services or need credentials.

## Working together

Start with [the team guide](team/README.md) and your individual task guide. Coding
agents discover this routing through the root `AGENTS.md` (the sole Markdown-location
exception); say your name and ask for your next unfinished task.

The first milestone's shared endpoint names, JSON examples and error behaviour are in
[API.md](API.md). Frontend mocks and backend routes should follow that contract.

1. Start a focused branch from the team's agreed shared base, `dev`.
   Use `feat/<short-task>`, `fix/<short-task>` or `docs/<short-task>`.
2. Agree on API request/response shapes before implementing connected screens and routes.
   Keep implemented routes documented by FastAPI's OpenAPI schema; record proposed
   contracts in the PR before either pair depends on them.
3. Each pair divides files/tasks between themselves; avoid both editing the same screen
   or route simultaneously. Share small PRs frequently rather than one large final PR.
4. Ask the other pair to review interface changes; request Zhihao's final review for
   integration and merging. Do not push directly to the shared branch.
5. Update the relevant lockfile when changing dependencies and include it in the PR.
   Use npm only in `frontend/`, and uv only in `backend/`.

These are team conventions, not enforced repository permissions. Zhihao can configure
GitHub branch rules requiring CI and review separately. No remote branch protection,
collaborator permissions or CODEOWNERS usernames have been configured by this setup.

Never commit credentials or real student resumes. Future database/LLM credentials
belong on the backend only; client-delivered variables are public. Use synthetic
fixtures in tests. Authentication and per-user access checks are required before
implementing real user-data endpoints.

## Layout and design references

For the initial Supabase tables, see [database setup](DB/README.md) and
[001_initial_schema.sql](DB/001_initial_schema.sql). Creating tables does not yet connect
the Python application to them.

```text
frontend/src/                  React UI (TypeScript)
backend/app/                   FastAPI application (Python)
backend/tests/                 API tests
backend/.env.example           Safe backend configuration template
.github/                       CI workflow
docs/erd.md                    Current provisional schema and relationships
docs/PRD.md                    MVP scope, acceptance criteria and open decisions
docs/pull-request-template.md  Pull-request review checklist reference
```

Framework references: [Vite](https://vite.dev/guide/),
[FastAPI](https://fastapi.tiangolo.com/tutorial/first-steps/),
[uv projects](https://docs.astral.sh/uv/guides/projects/).
