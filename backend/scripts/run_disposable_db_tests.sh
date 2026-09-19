#!/usr/bin/env bash

set -Eeuo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
backend_dir="$repo_root/backend"
schema_file="$repo_root/docs/DB/001_initial_schema.sql"

container_name="inf2003-postgres-test-$$-$RANDOM"
container_id=""
host_port=""

cleanup() {
    if [[ -n "$container_id" ]]; then
        docker rm --force "$container_id" >/dev/null 2>&1 || true
    fi
}

trap 'status=$?; cleanup; exit "$status"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# This password is disposable and is used only inside the local test container.
if ! container_id=$(docker run \
        --detach \
        --rm \
        --name "$container_name" \
        --publish 127.0.0.1::5432 \
        --env POSTGRES_PASSWORD=postgres \
        postgres:16); then
    printf 'Unable to start the disposable PostgreSQL container.\n' >&2
    exit 1
fi

for _ in {1..60}; do
    mapping=$(docker port "$container_name" 5432/tcp 2>/dev/null || true)
    if [[ "$mapping" =~ 127\.0\.0\.1:([0-9]+) ]]; then
        host_port="${BASH_REMATCH[1]}"
        break
    fi
    sleep 1
done

if [[ -z "$host_port" ]]; then
    printf 'Unable to determine the disposable container port.\n' >&2
    exit 1
fi

for _ in {1..60}; do
    if docker exec "$container_name" pg_isready \
        --host 127.0.0.1 --username postgres --dbname postgres \
        >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

if ! docker exec "$container_name" pg_isready \
    --host 127.0.0.1 --username postgres --dbname postgres \
    >/dev/null 2>&1; then
    printf 'Disposable PostgreSQL did not become ready.\n' >&2
    exit 1
fi

# The bootstrap expects Supabase Auth's schema/table and standard roles. The
# roles are local test prerequisites only; the application tests connect as
# postgres through the generated loopback DSN below.
docker exec --interactive "$container_name" psql \
    --username postgres \
    --dbname postgres \
    --set=ON_ERROR_STOP=1 <<'SQL'
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

docker exec --interactive "$container_name" psql \
    --username postgres \
    --dbname postgres \
    --set=ON_ERROR_STOP=1 < "$schema_file"

test_database_url="postgresql://postgres:postgres@127.0.0.1:${host_port}/postgres"
cd "$backend_dir"

# Keep the integration suite pointed only at the generated local database. uv
# must not read backend/.env, and DATABASE_URL must not leak in from the shell.
env -u DATABASE_URL -u TEST_DATABASE_URL \
    TEST_DATABASE_URL="$test_database_url" \
    uv run --no-env-file --no-sync pytest -q --confcutdir=tests
