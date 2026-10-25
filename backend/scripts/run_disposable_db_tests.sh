#!/usr/bin/env bash

set -Eeuo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
backend_dir="$repo_root/backend"
schema_file="$repo_root/docs/DB/001_initial_schema.sql"

container_name="inf2003-postgres-test-$$-$RANDOM"
container_id=""
host_port=""

mongo_container_name="inf2003-mongo-test-$$-$RANDOM"
mongo_container_id=""
mongo_host_port=""
mongo_test_database="jobless_simulator_test"

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

# Disposable MongoDB for the document tests: no auth, loopback only, removed by
# the same cleanup trap. The production validators and indexes are loaded into
# the test database so fixtures are checked exactly like real documents.
if ! mongo_container_id=$(docker run \
        --detach \
        --rm \
        --name "$mongo_container_name" \
        --publish 127.0.0.1::27017 \
        mongo:7); then
    printf 'Unable to start the disposable MongoDB container.\n' >&2
    exit 1
fi

for _ in {1..60}; do
    mapping=$(docker port "$mongo_container_name" 27017/tcp 2>/dev/null || true)
    if [[ "$mapping" =~ 127\.0\.0\.1:([0-9]+) ]]; then
        mongo_host_port="${BASH_REMATCH[1]}"
        break
    fi
    sleep 1
done

if [[ -z "$mongo_host_port" ]]; then
    printf 'Unable to determine the disposable MongoDB port.\n' >&2
    exit 1
fi

mongo_ready=""
for _ in {1..60}; do
    if docker exec "$mongo_container_name" \
        mongosh --quiet --eval 'db.runCommand({ping:1})' >/dev/null 2>&1; then
        mongo_ready=1
        break
    fi
    sleep 1
done

if [[ -z "$mongo_ready" ]]; then
    printf 'Disposable MongoDB did not become ready.\n' >&2
    exit 1
fi

docker cp "$repo_root/docs/DB/001_initial_collections.js" \
    "$mongo_container_name:/tmp/001_initial_collections.js" >/dev/null
docker exec "$mongo_container_name" \
    mongosh --quiet "$mongo_test_database" /tmp/001_initial_collections.js

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
test_mongodb_uri="mongodb://127.0.0.1:${mongo_host_port}/"
cd "$backend_dir"

# Keep the integration suite pointed only at the generated local database. uv
# must not read backend/.env, and DATABASE_URL / MONGODB_URI must not leak in
# from the shell.
env -u DATABASE_URL -u TEST_DATABASE_URL -u MONGODB_URI -u MONGODB_DATABASE -u TEST_MONGODB_URI \
    TEST_DATABASE_URL="$test_database_url" \
    TEST_MONGODB_URI="$test_mongodb_uri" \
    uv run --no-env-file --no-sync pytest -q --confcutdir=tests
