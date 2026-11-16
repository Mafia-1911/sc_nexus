#!/usr/bin/env bash
# Copy the local database (compose `db`) to Neon, once (A-119). Run from the repo root with the
# stack up. Needs NEON_DATABASE_URL (the direct, non-pooled URL) in .env. Neon's free tier holds
# 0.5 GB; the script prints the size it would copy first. Values are never printed.
set -euo pipefail
cd "$(dirname "$0")/.."
NEON="$(grep -E '^"?NEON_DATABASE_URL"?=' .env | head -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//')"
[ -n "$NEON" ] || { echo "NEON_DATABASE_URL missing in .env"; exit 1; }
PG="docker run --rm -i -e PGCONNECT_TIMEOUT=20 postgres:17-alpine"

echo "local size: $(docker compose exec -T db psql -U cportal -d cportal -tAc "select pg_size_pretty(pg_database_size('cportal'))")"
$PG psql "$NEON" -v ON_ERROR_STOP=1 -qc "create extension if not exists postgis; create extension if not exists vector;"
if [ "$($PG psql "$NEON" -tAc "select count(*) from information_schema.tables where table_name='alembic_version'")" != "0" ]; then
  echo "Neon already has the schema; not copying again (drop it first to recopy)."; exit 0
fi
# Custom-format dump streamed straight into Neon; extensions exist already, ownership is Neon's.
docker compose exec -T db pg_dump -U cportal -d cportal -Fc --no-owner --no-privileges \
  --exclude-schema=tiger --exclude-schema=tiger_data --exclude-schema=topology \
  | $PG pg_restore --no-owner --no-privileges --exit-on-error -d "$NEON" 2>&1 \
  | grep -v 'already exists' || true
echo "Neon size: $($PG psql "$NEON" -tAc "select pg_size_pretty(pg_database_size(current_database()))")"
