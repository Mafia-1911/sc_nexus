#!/usr/bin/env bash
# User-level Postgres 16 + PostGIS + pgvector without Docker (A-023), for M1 and for laptops
# where the Docker socket is not available. docker compose stays the primary runtime (M2).
#
#   scripts/db-local.sh install   # conda-forge packages via micromamba (~470 MB, no sudo)
#   scripts/db-local.sh init      # create the cluster, role "cportal" and databases
#   scripts/db-local.sh start | stop | status | psql
#
# The data directory lives on a POSIX filesystem (default under ~/.local/share), never on the
# repo's NTFS drive: Postgres needs 0700 permissions on it.
set -euo pipefail

ROOT="${CPORTAL_LOCAL_ROOT:-$HOME/.local/share/cportal}"
PREFIX="$ROOT/pg"
PGDATA="$ROOT/pgdata"
PORT="${CPORTAL_PG_PORT:-5432}"
BIN="$PREFIX/bin"
MAMBA="${MAMBA_EXE:-$HOME/.local/bin/micromamba}"

need_bin() {
  [[ -x "$BIN/pg_ctl" ]] || { echo "Postgres not installed; run: $0 install" >&2; exit 1; }
}

case "${1:-status}" in
  install)
    if [[ ! -x "$MAMBA" ]]; then
      mkdir -p "$(dirname "$MAMBA")"
      curl -fsSL https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xj -C /tmp bin/micromamba
      mv /tmp/bin/micromamba "$MAMBA"
    fi
    MAMBA_ROOT_PREFIX="$ROOT/mamba" "$MAMBA" create -y -p "$PREFIX" -c conda-forge \
      --override-channels 'postgresql=16' postgis pgvector
    ;;
  init)
    need_bin
    if [[ -f "$PGDATA/PG_VERSION" ]]; then echo "cluster exists: $PGDATA"; exit 0; fi
    "$BIN/initdb" -D "$PGDATA" -U postgres --auth=trust --encoding=UTF8 --locale=C >/dev/null
    printf "listen_addresses = 'localhost'\nport = %s\nunix_socket_directories = '/tmp'\n" \
      "$PORT" >> "$PGDATA/postgresql.conf"
    "$0" start
    # Like the postgis image's POSTGRES_USER, the app role is a superuser in dev.
    "$BIN/psql" -h localhost -p "$PORT" -U postgres -qc \
      "CREATE ROLE cportal LOGIN SUPERUSER PASSWORD 'cportal';"
    for db in cportal cportal_test; do
      "$BIN/createdb" -h localhost -p "$PORT" -U postgres -O cportal "$db"
      "$BIN/psql" -h localhost -p "$PORT" -U postgres -d "$db" -qc \
        "CREATE EXTENSION IF NOT EXISTS postgis; CREATE EXTENSION IF NOT EXISTS vector;"
    done
    echo "ready: postgresql+psycopg://cportal:cportal@localhost:$PORT/cportal"
    ;;
  start)
    need_bin
    "$BIN/pg_ctl" -D "$PGDATA" -l "$ROOT/postgres.log" -w status >/dev/null 2>&1 \
      || "$BIN/pg_ctl" -D "$PGDATA" -l "$ROOT/postgres.log" -w start >/dev/null
    echo "postgres running on localhost:$PORT (log: $ROOT/postgres.log)"
    ;;
  stop)
    need_bin
    "$BIN/pg_ctl" -D "$PGDATA" -w stop
    ;;
  status)
    need_bin
    "$BIN/pg_ctl" -D "$PGDATA" status
    ;;
  psql)
    need_bin
    shift
    exec "$BIN/psql" -h localhost -p "$PORT" -U cportal -d cportal "$@"
    ;;
  *)
    echo "usage: $0 install|init|start|stop|status|psql" >&2
    exit 2
    ;;
esac
