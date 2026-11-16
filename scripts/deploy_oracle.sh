#!/usr/bin/env bash
# Deploy the backend (API + worker + Caddy) to the Oracle Cloud VM (A-119). Run from the repo root:
#   scripts/deploy_oracle.sh            # first run installs Docker on the VM, then deploys
# Needs in .env: ORACLE_VM_IP, ORACLE_VM_USER (default ubuntu), NEON_DATABASE_URL.
# Writes .env.prod on the VM (server-side keys, DATABASE_URL, API_TOKEN, API_HOST); values are
# never printed. The API token is generated once and kept in .env as API_TOKEN for Vercel.
set -euo pipefail
cd "$(dirname "$0")/.."
get() { grep -E "^\"?$1\"?=" .env | head -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"; }

IP="$(get ORACLE_VM_IP)"; USER_="$(get ORACLE_VM_USER)"; USER_="${USER_:-ubuntu}"
NEON="$(get NEON_DATABASE_URL)"
[ -n "$IP" ] || { echo "ORACLE_VM_IP missing in .env"; exit 1; }
[ -n "$NEON" ] || { echo "NEON_DATABASE_URL missing in .env"; exit 1; }
TOKEN="$(get API_TOKEN)"
if [ -z "$TOKEN" ]; then
  TOKEN="$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 40)"
  printf '\nAPI_TOKEN=%s\n' "$TOKEN" >> .env
  echo "generated API_TOKEN (saved in .env for Vercel)"
fi
HOST="${IP//./-}.sslip.io"
SSH="ssh -o StrictHostKeyChecking=accept-new $USER_@$IP"

# 1. Docker on the VM (once) and the firewall: Oracle's Ubuntu images block 80/443 in iptables.
$SSH 'command -v docker >/dev/null || (curl -fsSL https://get.docker.com | sudo sh && sudo usermod -aG docker $USER);
  sudo iptables -C INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null || sudo iptables -I INPUT 6 -p tcp --dport 80 -j ACCEPT;
  sudo iptables -C INPUT -p tcp --dport 443 -j ACCEPT 2>/dev/null || sudo iptables -I INPUT 6 -p tcp --dport 443 -j ACCEPT;
  sudo sh -c "command -v netfilter-persistent >/dev/null && netfilter-persistent save" || true;
  sudo mkdir -p /opt/cportal && sudo chown $USER /opt/cportal'

# 2. Code and the files git does not hold (C5 models and gallery; never the local .env).
git ls-files -z | rsync -az --from0 --files-from=- ./ "$USER_@$IP:/opt/cportal/"
rsync -az data/c5 models "$USER_@$IP:/opt/cportal/" --exclude '*.tmp'
rsync -az deploy/oracle/docker-compose.yml "$USER_@$IP:/opt/cportal/docker-compose.yml"

# 3. .env.prod: server-side keys plus the deployment's own settings (written remotely, 0600).
DB="${NEON/postgres:\/\//postgresql+psycopg:\/\/}"; DB="${DB/postgresql:\/\//postgresql+psycopg:\/\/}"
case "$DB" in *sslmode=*) ;; *\?*) DB="$DB&sslmode=require" ;; *) DB="$DB?sslmode=require" ;; esac
{
  grep -E '^"?(AIS_STREAM_APIKEY|GLOBAL_FISHING_WATCH_GFW_ACCESS_TOKEN|DATADOCKED_APIKEY|MAPBOX_API|RELIEFWEB_APPNAME|OPEN_FDA_APIKEY|UN_COMTRADE_APIKEY|NASA_FIRMS_MAPKEY|NASA_EARTHDATA_TOKEN|TOM_TOM_APIKEY)"?=' .env || true
  printf 'DATABASE_URL=%s\nAPI_TOKEN=%s\nAPI_HOST=%s\n' "$DB" "$TOKEN" "$HOST"
} | $SSH 'umask 077 && cat > /opt/cportal/.env.prod'

# 4. Build on the VM (ARM) and start; migrations run first.
$SSH 'cd /opt/cportal && sg docker -c "docker compose up -d --build"'
echo "API: https://$HOST  (set API_URL to this on Vercel; API_TOKEN is in .env)"
