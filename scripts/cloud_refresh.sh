#!/usr/bin/env bash
# Refresh the deployed site's live data in Neon (A-121): one short CPA poll, then disconnect, so
# Neon's compute can suspend between runs (an always-on worker would use up the free tier's
# compute hours). Hourly: schedule, berths, last 24 h. Every 6 h: yards, lying, daily reports.
# Run from anywhere; scheduled by `make cloud-refresh-timer` (a transient user timer).
set -euo pipefail
cd "$(dirname "$0")/.."
URL="$({ grep -E '^"?DATABASE_URL_UNPOOLED"?=' .env || true; } | head -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//')"
[ -n "$URL" ] || { echo "DATABASE_URL_UNPOOLED missing in .env"; exit 1; }
run() {
  docker run --rm -e DATABASE_URL="$URL" -e CPORTAL_ROOT=/app -v "$PWD/data/raw:/app/data/raw" \
    cportal-app:latest uv run --no-sync cpa-poll --set "$1" 2>&1 | grep -vi "postgres" | tail -3
}
run fast
if [ $(( $(date +%-H) % 6 )) -eq 0 ]; then
  run slow; run daily
  # News, hazard, tariff and other live feeds, then C2 events, the C6 tariff matrix and Nexus (every 6 h).
  docker run --rm -e DATABASE_URL="$URL" -e CPORTAL_ROOT=/app -e CPORTAL_LLM=0 \
    -v "$PWD/data/raw:/app/data/raw" -v "$PWD/.env:/app/.env:ro" cportal-app:latest \
    uv run --no-sync python -c "
from cportal_worker import c2, c6, nexus, sources
for ds in sorted(sources.live_sources()):
    try: sources.refresh(ds)
    except Exception as e: print(ds, 'failed', str(e)[:80])
print('c2', c2.process()); print('c6', c6.refresh()); print('nexus', 'ok' if nexus.refresh() else '-')
" 2>&1 | grep -vi "postgres" | tail -4
fi
echo "cloud refresh done $(date -Is)"
