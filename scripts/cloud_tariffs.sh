#!/usr/bin/env bash
# Load the Tariff Monitor (C6) into Neon once: apply migrations, replay the committed tariff
# samples (DS-TRADE-04..08, real data, no keys needed) and build the effective-rate matrix.
# Run after the C6 migrations reach Neon or after a fresh deploy_db.sh copy. Later updates come
# from scripts/cloud_refresh.sh (every 6 h). Needs DATABASE_URL_UNPOOLED in .env and the
# cportal-app image (`make up` builds it). Values are never printed.
set -euo pipefail
cd "$(dirname "$0")/.."
URL="$({ grep -E '^"?DATABASE_URL_UNPOOLED"?=' .env || true; } | head -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//')"
[ -n "$URL" ] || { echo "DATABASE_URL_UNPOOLED missing in .env"; exit 1; }
docker run --rm -e DATABASE_URL="$URL" -e CPORTAL_ROOT=/app -e CPORTAL_LLM=0 \
  -v "$PWD/data/raw:/app/data/raw" cportal-app:latest sh -c '
uv run --no-sync alembic -c db/alembic.ini upgrade head
for ds in DS-TRADE-04 DS-TRADE-05 DS-TRADE-06 DS-TRADE-07 DS-TRADE-08; do
  uv run --no-sync ingest --replay "$ds"
done
uv run --no-sync c6 refresh
' 2>&1 | grep -vi "postgres" | tail -6
echo "cloud tariffs done $(date -Is)"
