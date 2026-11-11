#!/usr/bin/env bash
# Local quick start: run Jobless Simulator on one machine with Docker, no Google,
# Supabase or MongoDB Atlas account needed. Meant for markers and new teammates.
#
#   bash backend/scripts/local_quickstart.sh up        # databases, schema, jobs, demo student
#   bash backend/scripts/local_quickstart.sh backend   # run the API against them (leave running)
#   cd frontend && npm run dev:quickstart              # the app, with "Continue as demo student"
#   bash backend/scripts/local_quickstart.sh down      # remove the containers and their data
#
# Everything stays on 127.0.0.1. The PostgreSQL password below is a throwaway for the
# local container only. The API runs with AUTH_ALLOW_UNVERIFIED_TOKENS=true, which the
# backend refuses under APP_ENV=production, so this setup cannot leak into a deployment.
# It never reads backend/.env and never touches the team's Supabase or Atlas projects.

set -Eeuo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
backend_dir="$repo_root/backend"

pg_container="jobless-quickstart-postgres"
mongo_container="jobless-quickstart-mongo"
pg_port=55432
mongo_port=57017
mongo_database="jobless_simulator"

# Must match DEMO_USER_ID in frontend/src/auth/localDemo.ts.
demo_user_id="7e57de30-0000-4000-8000-000000000001"
demo_name="Demo Student"

database_url="postgresql://postgres:postgres@127.0.0.1:${pg_port}/postgres"
mongodb_uri="mongodb://127.0.0.1:${mongo_port}/"

say() { printf '\n==> %s\n' "$*"; }
fail() { printf 'local_quickstart: %s\n' "$*" >&2; exit 1; }

running() {
    [[ "$(docker inspect --format '{{.State.Running}}' "$1" 2>/dev/null || true)" == "true" ]]
}

psql_run() {
    docker exec --interactive "$pg_container" psql --username postgres --dbname postgres \
        --set=ON_ERROR_STOP=1 --quiet "$@"
}

backend_env() {
    # Only these variables reach the backend; nothing is inherited from backend/.env.
    env -u SUPABASE_URL -u SUPABASE_JWT_SECRET -u DATABASE_URL -u MONGODB_URI \
        APP_ENV=development \
        AUTH_ALLOW_UNVERIFIED_TOKENS=true \
        DATABASE_URL="$database_url" \
        MONGODB_URI="$mongodb_uri" \
        MONGODB_DATABASE="$mongo_database" \
        BACKEND_ADMIN_USER_IDS="$demo_user_id" \
        "$@"
}

wait_for() {
    local what=$1
    shift
    for _ in {1..60}; do
        if "$@" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    fail "$what did not become ready within 60 seconds."
}

cmd_up() {
    command -v docker >/dev/null || fail "Docker is required (https://docs.docker.com/get-docker/)."
    command -v uv >/dev/null || fail "uv is required (see docs/USER_MANUAL.md, section 2)."
    docker info >/dev/null 2>&1 || fail "Docker is installed but not running. Start Docker Desktop and retry."

    if running "$pg_container" || running "$mongo_container"; then
        fail "The quick-start databases are already running. Use 'backend' to start the API, or 'down' then 'up' to start afresh."
    fi
    docker rm --force "$pg_container" "$mongo_container" >/dev/null 2>&1 || true

    say "Starting PostgreSQL 16 on 127.0.0.1:${pg_port} and MongoDB 7 on 127.0.0.1:${mongo_port}"
    docker run --detach --name "$pg_container" --publish "127.0.0.1:${pg_port}:5432" \
        --env POSTGRES_PASSWORD=postgres postgres:16 >/dev/null
    docker run --detach --name "$mongo_container" --publish "127.0.0.1:${mongo_port}:27017" \
        mongo:7 >/dev/null
    wait_for "PostgreSQL" docker exec "$pg_container" pg_isready --host 127.0.0.1 --username postgres
    wait_for "MongoDB" docker exec "$mongo_container" mongosh --quiet --eval 'db.runCommand({ping:1})'

    say "Creating the schema (docs/DB 001, 002 skills seed, 003) and MongoDB collections"
    # Supabase provides these roles and auth.users; a plain PostgreSQL needs stand-ins.
    psql_run <<'SQL'
CREATE ROLE anon NOBYPASSRLS;
CREATE ROLE authenticated NOBYPASSRLS;
CREATE ROLE service_role BYPASSRLS;
CREATE SCHEMA auth;
CREATE TABLE auth.users (id uuid PRIMARY KEY);
SQL
    psql_run < "$repo_root/docs/DB/001_initial_schema.sql" >/dev/null
    psql_run < "$repo_root/docs/DB/002_seed_skills.sql" >/dev/null
    psql_run < "$repo_root/docs/DB/003_views_triggers_indexes.sql" >/dev/null
    docker cp "$repo_root/docs/DB/001_initial_collections.js" \
        "$mongo_container:/tmp/001_initial_collections.js" >/dev/null
    docker exec "$mongo_container" mongosh --quiet "$mongo_database" /tmp/001_initial_collections.js >/dev/null

    local data_file
    data_file=$(ls "$repo_root"/data/raw/linkedin_sg_*.json 2>/dev/null | grep -v '_sample\.json$' | sort | tail -n 1 || true)
    if [[ -z "$data_file" ]]; then
        data_file="$backend_dir/tests/fixtures/linkedin_apify_sample.json"
        say "No export in data/raw/; loading the small fixture $data_file instead"
    else
        say "Loading jobs from ${data_file#"$repo_root"/} (takes a minute or two)"
    fi
    (cd "$backend_dir" && uv sync --locked --quiet &&
        backend_env uv run --no-env-file --no-sync python scripts/ingest_jobs.py --file "$data_file" |
        tail -n 6)

    say "Adding the demo student with a few skills and tracker rows"
    psql_run --set=uid="$demo_user_id" --set=name="$demo_name" <<'SQL'
INSERT INTO auth.users (id) VALUES (:'uid');
INSERT INTO public.users (user_id, full_name) VALUES (:'uid', :'name');
INSERT INTO public.user_skills (user_id, skill_id)
SELECT :'uid', skill_id FROM public.skills
 WHERE lower(name) IN ('python', 'sql', 'javascript', 'git', 'data visualization', 'communication');
-- Three of the best-covered active jobs, so the Vault has something to show.
INSERT INTO public.user_jobs (user_id, job_id, status)
SELECT :'uid', job_id, (ARRAY['SAVED', 'APPLIED', 'INTERVIEW'])[(row_number() OVER (ORDER BY n DESC, job_id))::int]
  FROM (SELECT j.job_id, count(*) AS n
          FROM public.jobs j JOIN public.job_skills js USING (job_id)
         WHERE j.is_active
         GROUP BY j.job_id
         ORDER BY n DESC, j.job_id
         LIMIT 3) top;
SELECT (SELECT count(*) FROM public.jobs WHERE is_active) AS active_jobs,
       (SELECT count(*) FROM public.job_skills) AS job_skill_links,
       (SELECT count(*) FROM public.user_skills WHERE user_id = :'uid') AS demo_skills,
       (SELECT count(*) FROM public.user_jobs WHERE user_id = :'uid') AS demo_tracker_rows;
SQL

    say "Ready. Next, in two terminals from the repository root:"
    printf '   1) bash backend/scripts/local_quickstart.sh backend\n'
    printf '   2) cd frontend && npm run dev:quickstart\n'
    printf '   Then open http://127.0.0.1:5173 and choose "Continue as demo student".\n'
}

cmd_backend() {
    running "$pg_container" && running "$mongo_container" ||
        fail "The quick-start databases are not running. Run 'up' first."
    say "API on http://127.0.0.1:8000 (Ctrl+C to stop). Development sign-in is enabled."
    cd "$backend_dir"
    backend_env uv run --no-env-file --locked \
        uvicorn app.main:app --host 127.0.0.1 --port 8000
}

cmd_down() {
    docker rm --force "$pg_container" "$mongo_container" >/dev/null 2>&1 || true
    say "Removed the quick-start containers and their data."
}

case "${1:-}" in
    up) cmd_up ;;
    backend) cmd_backend ;;
    down) cmd_down ;;
    *)
        printf 'Usage: bash backend/scripts/local_quickstart.sh {up|backend|down}\n' >&2
        exit 2
        ;;
esac
