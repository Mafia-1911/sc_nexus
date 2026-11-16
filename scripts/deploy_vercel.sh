#!/usr/bin/env bash
# Deploy the website (apps/web) to Vercel (A-119). Run from the repo root after deploy_oracle.sh.
# Needs in .env: VERCEL_TOKEN, API_TOKEN (written by deploy_oracle.sh), ORACLE_VM_IP and
# NEON_POOLED_URL (logins). Generates AUTH_SECRET once (kept in .env). Values are never printed.
set -euo pipefail
cd "$(dirname "$0")/.."
get() { grep -E "^\"?$1\"?=" .env | head -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"; }
T="$(get VERCEL_TOKEN)"; IP="$(get ORACLE_VM_IP)"; TOKEN="$(get API_TOKEN)"; POOLED="$(get NEON_POOLED_URL)"
for v in T IP TOKEN POOLED; do [ -n "${!v}" ] || { echo "missing: $v (see docs/USER_TASKS.md)"; exit 1; }; done
SECRET="$(get AUTH_SECRET)"
if [ -z "$SECRET" ]; then
  SECRET="$(head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 48)"
  printf '\nAUTH_SECRET=%s\n' "$SECRET" >> .env
fi
VERCEL="npx --yes vercel@65.9.0"
cd apps/web
$VERCEL link --yes --project cportal --token "$T" >/dev/null
setenv() {  # name value: replace the production value
  $VERCEL env rm "$1" production --yes --token "$T" >/dev/null 2>&1 || true
  printf '%s' "$2" | $VERCEL env add "$1" production --token "$T" >/dev/null
}
setenv API_URL "https://${IP//./-}.sslip.io"
setenv API_TOKEN "$TOKEN"
setenv AUTH_SECRET "$SECRET"
setenv AUTH_DATABASE_URL "$POOLED"
setenv NEXT_PUBLIC_WS_URL "off"
setenv NEXT_PUBLIC_MAP_SOURCE "online"
$VERCEL deploy --prod --yes --token "$T"
