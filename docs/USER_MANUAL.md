# Jobless Simulator user manual

This manual takes you from a fresh laptop to a running copy of the app, using your own
Supabase project and your own MongoDB Atlas cluster. Follow sections 1 to 7 in order.

## 1. What the app is

Jobless Simulator helps a student find relevant internships and jobs, record decisions
(save, skip, applied, interview, offer), and see which skills a target role asks for that
they do not have yet.

```text
Browser  ->  React + Vite (port 5173)  ->  FastAPI (port 8000)  ->  Supabase PostgreSQL
                  |                                          \->  MongoDB Atlas
                  \-> Supabase Auth (Google sign-in; the browser holds the session)
```

- PostgreSQL (relational): users, skills, jobs, job-skill links and each user's decisions.
- MongoDB (documents): the full job description with its extracted skill requirements,
  and uploaded resume text.
- The browser talks only to the FastAPI backend (through the `/api` proxy) and to
  Supabase Auth. It never receives a database password.

## 2. Prerequisites

| Tool | Version | Used for |
|---|---|---|
| Git | any recent | clone the repository |
| Node.js and npm | 22.12 or newer on the 22.x line (`.nvmrc` says `22`; `frontend/package.json` requires `>=22.12.0`) | frontend |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | any recent | backend; installs the pinned Python (`backend/.python-version` is `3.12`; `backend/pyproject.toml` allows `>=3.12,<3.15`) |
| Docker | any recent | only for the optional database tests in section 9 |
| `mongosh` | any recent | run the MongoDB setup script in section 4 |

You also need a Google account, a free Supabase account and a free MongoDB Atlas account.

Clone the repository and install dependencies from its root:

```sh
cd frontend
npm ci
cd ../backend
uv sync --locked
```

`uv run` uses `backend/.venv` automatically; no activation step is needed.

## 3. Supabase setup (PostgreSQL and sign-in)

### 3.1 Create the project

1. In the Supabase dashboard create a new project. Save the database password you choose;
   you need it in step 3.4.
2. Wait until the project finishes provisioning.

### 3.2 Create the tables

Open **SQL Editor** and run these three files from `docs/DB/`, **in this order**, each
pasted whole and run once:

1. `001_initial_schema.sql` creates the six tables (`users`, `skills`, `jobs`,
   `user_skills`, `job_skills`, `user_jobs`).
2. `002_seed_skills.sql` loads the skill dictionary (safe to re-run; it skips existing names).
3. `003_views_triggers_indexes.sql` adds triggers, two views and indexes.

`001` and `003` are bootstrap scripts, not upgrade scripts: if an object already exists they
fail and roll back. Do not drop tables to re-run them; start from a fresh project instead.
Check in **Table Editor** that the six tables exist and `skills` has rows.

### 3.3 Enable Google sign-in

1. In Google Cloud Console create an OAuth client of type "Web application". Under
   "Authorized redirect URIs" add the callback URL shown on the Supabase page in the next
   step (it looks like `https://<project-ref>.supabase.co/auth/v1/callback`).
2. In Supabase open **Authentication -> Sign In / Providers -> Google**, enable it and paste
   the Google client ID and secret.
3. In **Authentication -> URL Configuration** set **Site URL** to `http://127.0.0.1:5173`
   and add `http://127.0.0.1:5173/auth/callback` to **Redirect URLs**. The app sends the
   student to `<browser origin>/auth/callback` after Google consent
   (`frontend/src/lib/supabase.ts`), so the host you type in the browser must match:
   always open the app at `http://127.0.0.1:5173`, not `localhost`, unless you also add
   `http://localhost:5173/auth/callback`.

### 3.4 Collect the three values you need

| Value | Where | Goes into |
|---|---|---|
| Project URL | **Project Settings -> Data API -> Project URL**, e.g. `https://<project-ref>.supabase.co`. Use the base URL only: it must **not** end in `/rest/v1/`. | `SUPABASE_URL` and `VITE_SUPABASE_URL` |
| Publishable key | **Project Settings -> API Keys -> Publishable key** (starts with `sb_publishable_`). If only legacy keys are shown, use the `anon` `public` key. | `VITE_SUPABASE_PUBLISHABLE_KEY` |
| Postgres URI | **Connect** dialog, **Session pooler** connection string. Replace the password placeholder with your database password. | `DATABASE_URL` |

Why the Session pooler: the "Direct connection" host is IPv6-only on many plans, so it fails
with a name or network error on IPv4-only home and campus networks. The Session pooler works
over IPv4 and keeps the session semantics the backend relies on. Copy the URI exactly as
shown; do not edit the host. The user in it looks like `postgres.<project-ref>`.

Never put a secret key (`sb_secret_...`, `service_role`), the database password or the
MongoDB URI in any `VITE_` variable: Vite ships those to the browser.

## 4. MongoDB Atlas setup

1. Create a free cluster in Atlas.
2. **Database Access -> Add New Database User**: choose a username and password, with
   read and write access to any database. Avoid `@`, `:` or `/` in the password, or
   URL-encode them in the connection string.
3. **Network Access -> Add IP Address -> Add Current IP Address**. This must be the public
   IP your terminal actually uses. If you run a VPN, iCloud Private Relay or a campus proxy
   that changes your outbound IP, turn it off first or add that IP as well. Without this
   entry the backend cannot connect (see section 10).
4. **Connect -> Drivers** (or **Shell**) shows the connection string, which looks like
   `mongodb+srv://<user>:<password>@<cluster-host>/`. Fill in the user and password.
   This is your `MONGODB_URI`.
5. Create the collections and validators. From the **repository root**, with `mongosh`
   installed (`docs/DB/README.md` describes this script):

   ```sh
   mongosh "<your MONGODB_URI>"
   ```

   Then, inside mongosh:

   ```javascript
   use jobless_simulator
   db.getName()
   load('docs/DB/001_initial_collections.js')
   ```

   The script creates `resume_documents` and `job_documents` with validators and unique
   indexes. It refuses the `test` database and stops if either collection already exists;
   do not re-run it on a populated database.
6. Create the job title search indexes (safe to re-run). This needs `backend/.env`
   from section 5, so do it after that step, from `backend/`:

   ```sh
   uv run --env-file .env python app/create_search_indexes.py
   ```

   Expected output: `Indexes created (or already existed) on job_documents.title`.

## 5. Environment files

Neither file is committed; git ignores them. Copy the templates:

```sh
cp frontend/.env.example frontend/.env.local
cp backend/.env.example backend/.env
```

On Windows PowerShell use `Copy-Item` instead of `cp`.

### 5.1 `backend/.env`

| Variable | Required | Meaning and source |
|---|---|---|
| `APP_ENV` | no | `development` (default). Use `production` only when deploying. |
| `AUTH_ALLOW_UNVERIFIED_TOKENS` | no | Leave `false`. `true` skips token verification (development bypass; the app refuses to start with it under `APP_ENV=production`). |
| `DATABASE_URL` | yes | Supabase Session pooler URI (section 3.4). Without it, job, skill and profile routes fail; only an in-memory profile fallback works. |
| `SUPABASE_URL` | yes | Project URL, identical to `VITE_SUPABASE_URL`. The backend fetches Supabase's public signing keys from it to verify sign-in tokens. |
| `SUPABASE_JWT_SECRET` | no | Only for a legacy project that still signs tokens with a shared HS256 secret. Leave commented out otherwise. |
| `MONGODB_URI` | yes | Atlas connection string (section 4). |
| `MONGODB_DATABASE` | no | Database name; default `jobless_simulator`. Must match the database you ran the setup script in. |
| `BACKEND_ADMIN_USER_IDS` | no | Comma-separated Supabase user UUIDs allowed to call admin HTTP routes. Find a UUID in **Authentication -> Users** after that person has signed in once. The ingestion command in section 7 does not need it. |
| `TEST_DATABASE_URL` | no | Leave unset. The disposable test script supplies its own. Never point it at your real project. |
| `APIFY_TOKEN` | no | Only for `scripts/fetch_linkedin_apify.py` (paid LinkedIn scraping, optional data preparation). |

### 5.2 `frontend/.env.local`

| Variable | Required | Meaning and source |
|---|---|---|
| `VITE_SUPABASE_URL` | yes | Project URL, base only (section 3.4). |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | yes | Publishable (or legacy anon) key. Safe for browsers. |
| `VITE_DATA` | no | Set to `mock` to show built-in synthetic data in Discover, Vault and Skill Gap without any backend job data (useful for a quick look). Leave unset for the real API. |
| `VITE_API_BASE_URL` | no | Leave unset: requests go to `/api`, which the Vite dev server forwards to `127.0.0.1:8000` (`frontend/vite.config.ts`). |

Restart `npm run dev` after every edit of `frontend/.env.local`; Vite reads it only at startup.

## 6. Run the app

Open two terminals, each starting in the repository root.

Backend (terminal 1):

```sh
cd backend
uv run --env-file .env --locked uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend (terminal 2):

```sh
cd frontend
npm run dev
```

| URL | What |
|---|---|
| http://127.0.0.1:5173 | the app |
| http://127.0.0.1:8000/api/health | backend health, returns `{"status": "ok", ...}` |
| http://127.0.0.1:8000/docs | interactive API documentation |

Check the proxy: `http://127.0.0.1:5173/api/health` should return the same health JSON.

Open `http://127.0.0.1:5173` and choose Google sign-in. The first time, the app asks what to
call you (onboarding) and then opens Discover. Discover will be empty until you load jobs.

## 7. Load job data (administrator command)

Jobs are loaded from the command line, by a person who has `backend/.env` filled in. Run
from `backend/`. Two modes (they cannot be combined):

Public job APIs, no API key needed (known sources: `arbeitnow`, `ai_dev_jobs`;
default is `arbeitnow`; default limit 50 per source):

```sh
cd backend
uv run --env-file .env python scripts/ingest_jobs.py --sources arbeitnow ai_dev_jobs --limit-per-source 200
```

A LinkedIn export file (source `linkedin_apify`; makes no network call; the file path is
yours, for example one produced by `scripts/fetch_linkedin_apify.py`):

```sh
cd backend
uv run --env-file .env python scripts/ingest_jobs.py --file ../data/raw/<export>.json
```

On success the command prints a JSON summary and exits with code 0:

```json
{
  "requested": 200,
  "inserted": 180,
  "updated": 0,
  "rejected": 20,
  "errors": ["..."]
}
```

`rejected` records are skipped individually with a short message in `errors`; the rest are
stored. Exit code 1 means total failure (nothing stored plus an error, or an unreachable
database or unreadable file); the first line printed starts with `Ingestion failed:`.

Running it again is safe: jobs are matched on `(source, external_job_id)`, so a repeat
updates the existing job and its MongoDB document and counts under `updated` instead of
creating duplicates. Allow a few minutes for large files; if it is extremely slow, see
section 10.

## 8. Demo walkthrough

1. **Onboarding.** On first sign-in enter the name to show in the app. You then land on
   Discover. The sidebar (tab bar on a phone) has Discover, Vault, Skill Gap and Profile.
2. **Discover.** Shows active jobs you have not decided on, best skill match first. Each card
   has a skill match meter and lists of matched and missing skills. Use **Filters** to filter
   by keyword, job type, work arrangement and location, then **Apply filters**. Press
   **Save** or the right arrow key to save a job; **Not interested** or the left arrow key
   to skip it. Either way the job leaves the feed.
3. **Vault.** Your decisions grouped by status tabs with counts: Saved, Applied, Interview,
   Offer, Rejected, Not interested. Move a job between statuses with the status selector on
   its row; remove a decision to let the job reappear in Discover.
4. **Skill Gap.** Choose a target role in **Target role**. The page shows how many of the
   role's top skills you have and ranks skills by the share of postings that ask for them,
   marking those you already have.
5. **Profile.** Change your display name and see your account. Under **Resume and skills**:
   - **Upload resume** (PDF or DOCX, up to 5 MB). The app checks the type and size before
     sending. The backend stores the resume text in MongoDB and extracts its skills.
   - **Skills found in your resume** lists the extracted skills that match the skills
     dictionary and that you have not confirmed yet, all ticked. Untick any that are wrong,
     then **Add selected**. Each skill is saved to your profile in PostgreSQL; a skill that
     fails to save shows **Not saved** with a retry button, and the others stay saved.
   - **Replace resume** uploads a new file. You keep one current resume; the new one replaces
     it. If the skills database is unavailable the upload fails and the old resume stays.
   - The skill editor below adds or removes skills by hand. Confirmed skills drive Discover's
     skill match and the Skill Gap "You have this" marks. In Skill Gap you can also tick
     "I already have this skill" on a gap, then **Add to my skills**.

## 9. Run the tests

Backend (no databases needed; tests that need PostgreSQL are skipped):

```sh
cd backend
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest
```

Database tests against throwaway containers (needs Docker running; from the repository root;
it starts PostgreSQL and MongoDB containers and removes them afterwards, never touching your
Supabase or Atlas projects):

```sh
bash backend/scripts/run_disposable_db_tests.sh
```

Frontend:

```sh
cd frontend
npm test
npm run build
```

`npm test` runs Vitest; `npm run build` type-checks and builds.

## 10. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Error "SQL job synchronization is unavailable." | `DATABASE_URL` is missing or wrong in `backend/.env`, or the backend was not started with `--env-file .env`. Fix it and restart the backend. |
| Mongo error "SSL handshake failed" / "tlsv1 alert internal error" | Your IP is not on the Atlas allow-list (section 4 step 3), or the cluster is paused, or a VPN, proxy or Private Relay is changing or intercepting your connection. Add the IP your terminal uses, resume the cluster, or switch the VPN off. |
| "No API key found" on sign-in | `VITE_SUPABASE_URL` or `VITE_SUPABASE_PUBLISHABLE_KEY` is wrong or missing. The URL must be the base URL without `/rest/v1/`. Fix `frontend/.env.local` and restart `npm run dev`. |
| Edits to `frontend/.env.local` have no effect | Vite reads it only at startup. Stop and restart `npm run dev`. |
| Sign-in bounces back to the home page | Your computer clock is wrong. The backend tolerates 30 seconds of skew (`backend/app/auth.py`); beyond that tokens look "not yet valid". Turn on automatic date and time sync. |
| Sign-in page says Supabase is not configured | Both `VITE_` values are required in `frontend/.env.local` (section 5.2). |
| Google shows "redirect_uri_mismatch" or returns to the wrong site | The Google redirect URI (section 3.3 step 1) or the Supabase Redirect URLs (step 3) are missing or use another host. Open the app at `http://127.0.0.1:5173`. |
| Database connection error that names a host or "Network is unreachable" | You used the Direct connection URI on an IPv4-only network. Use the Session pooler URI (section 3.4). |
| Import is extremely slow | MongoDB is unreachable, so every job waits for connection timeouts. Fix the Atlas allow-list or `MONGODB_URI` first. |
| "Document storage is not configured." | `MONGODB_URI` is empty. |
| Discover and Skill Gap are empty | No jobs loaded yet (section 7), or the backend is not running. |
| `npm run dev` or `uvicorn` reports the port is in use | Another copy is running. Stop it (the Vite proxy expects the backend on 8000). |
| Admin routes return 403 | Your user UUID is not in `BACKEND_ADMIN_USER_IDS`. |

To test only the Atlas connection, run `uv run python scripts/check_mongodb_connection.py`
from `backend/` (it reads `MONGODB_URI` from `backend/.env` and prints success or failure).

## 11. Performance benchmarks (optional)

The numbers in the report's performance section come from a benchmark that runs only on
throwaway local Docker databases with synthetic data; it never touches your Supabase or Atlas
projects and reads no `.env` file. With Docker running, from the repository root:

```sh
bash backend/scripts/run_benchmark.sh
```

It takes about 10 to 15 minutes, removes its containers when it finishes (also on Ctrl+C), and
writes `docs/perf/results-<today>.md` (for example `results-2026-10-27.md`), so it never overwrites an
earlier committed run. `BENCH_SIZES=5000` runs only the 5,000-job size,
which is faster. What each case measures and how to read the tables:
[docs/perf/README.md](perf/README.md).
