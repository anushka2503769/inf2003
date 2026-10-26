#!/usr/bin/env bash
# One command: throwaway postgres:16 + mongo:7 on random localhost ports, apply
# docs/DB 001/002/003 and the Mongo collections script (same approach as
# run_disposable_db_tests.sh), seed, run the WP-10 benchmark, write the results file,
# and remove both containers on exit.
#
#   bash backend/scripts/run_benchmark.sh               # 5,000 jobs and a 50,000-job run
#   BENCH_SIZES=5000 bash backend/scripts/run_benchmark.sh
#   BENCH_OUT=/some/path.md bash backend/scripts/run_benchmark.sh

set -Eeuo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
backend_dir="$repo_root/backend"
db_dir="$repo_root/docs/DB"
sizes="${BENCH_SIZES:-5000,50000}"
out_file="${BENCH_OUT:-$repo_root/docs/perf/results-2026-10-26.md}"
mongo_database="jobless_simulator_bench"

container_name="inf2003-postgres-bench-$$-$RANDOM"
mongo_container_name="inf2003-mongo-bench-$$-$RANDOM"
container_id=""
mongo_container_id=""
host_port=""
mongo_host_port=""

cleanup() {
    if [[ -n "$container_id" ]]; then
        docker rm --force "$container_id" >/dev/null 2>&1 || true
    fi
    if [[ -n "$mongo_container_id" ]]; then
        docker rm --force "$mongo_container_id" >/dev/null 2>&1 || true
    fi
}

trap 'status=$?; cleanup; exit "$status"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

wait_for_port() { # container, internal port -> prints the 127.0.0.1 host port
    local name=$1 internal=$2 mapping
    for _ in {1..60}; do
        mapping=$(docker port "$name" "$internal/tcp" 2>/dev/null || true)
        if [[ "$mapping" =~ 127\.0\.0\.1:([0-9]+) ]]; then
            printf '%s' "${BASH_REMATCH[1]}"
            return 0
        fi
        sleep 1
    done
    return 1
}

# Disposable password, used only inside this throwaway container.
if ! container_id=$(docker run --detach --rm --name "$container_name" \
        --publish 127.0.0.1::5432 --env POSTGRES_PASSWORD=postgres postgres:16); then
    printf 'Unable to start the disposable PostgreSQL container.\n' >&2
    exit 1
fi
if ! mongo_container_id=$(docker run --detach --rm --name "$mongo_container_name" \
        --publish 127.0.0.1::27017 mongo:7); then
    printf 'Unable to start the disposable MongoDB container.\n' >&2
    exit 1
fi

host_port=$(wait_for_port "$container_name" 5432) || {
    printf 'Unable to determine the disposable PostgreSQL port.\n' >&2; exit 1; }
mongo_host_port=$(wait_for_port "$mongo_container_name" 27017) || {
    printf 'Unable to determine the disposable MongoDB port.\n' >&2; exit 1; }

pg_ready=""
for _ in {1..60}; do
    if docker exec "$container_name" pg_isready --host 127.0.0.1 --username postgres \
        --dbname postgres >/dev/null 2>&1; then
        pg_ready=1
        break
    fi
    sleep 1
done
[[ -n "$pg_ready" ]] || { printf 'Disposable PostgreSQL did not become ready.\n' >&2; exit 1; }

mongo_ready=""
for _ in {1..60}; do
    if docker exec "$mongo_container_name" mongosh --quiet --eval 'db.runCommand({ping:1})' \
        >/dev/null 2>&1; then
        mongo_ready=1
        break
    fi
    sleep 1
done
[[ -n "$mongo_ready" ]] || { printf 'Disposable MongoDB did not become ready.\n' >&2; exit 1; }

docker cp "$db_dir/001_initial_collections.js" \
    "$mongo_container_name:/tmp/001_initial_collections.js" >/dev/null
docker exec "$mongo_container_name" \
    mongosh --quiet "$mongo_database" /tmp/001_initial_collections.js

# Supabase stand-ins the schema expects: the standard roles and auth.users. Local only.
docker exec --interactive "$container_name" psql --username postgres --dbname postgres \
    --set=ON_ERROR_STOP=1 --quiet <<'SQL'
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon') THEN
        CREATE ROLE anon;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
        CREATE ROLE authenticated;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'service_role') THEN
        CREATE ROLE service_role;
    END IF;
END
$$;

ALTER ROLE anon NOBYPASSRLS;
ALTER ROLE authenticated NOBYPASSRLS;
ALTER ROLE service_role BYPASSRLS;

CREATE SCHEMA auth;
CREATE TABLE auth.users (
    id uuid PRIMARY KEY
);
SQL

# 001 schema, 002 skill dictionary (the seed draws requirements from it), 003 views/indexes.
for migration in 001_initial_schema.sql 002_seed_skills.sql 003_views_triggers_indexes.sql; do
    docker exec --interactive "$container_name" psql --username postgres --dbname postgres \
        --set=ON_ERROR_STOP=1 --quiet < "$db_dir/$migration" >/dev/null
done

database_url="postgresql://postgres:postgres@127.0.0.1:${host_port}/postgres"
mongodb_uri="mongodb://127.0.0.1:${mongo_host_port}/"
mkdir -p "$(dirname -- "$out_file")"
cd "$backend_dir"

# uv must not read backend/.env, and nothing may leak in from the shell.
env -u DATABASE_URL -u TEST_DATABASE_URL -u MONGODB_URI -u MONGODB_DATABASE -u TEST_MONGODB_URI \
    uv run --locked --no-env-file python scripts/benchmark.py \
        --database-url "$database_url" \
        --mongodb-uri "$mongodb_uri" \
        --mongodb-database "$mongo_database" \
        --sizes "$sizes" \
        --out "$out_file" \
        ${BENCH_EXTRA_ARGS:-}
