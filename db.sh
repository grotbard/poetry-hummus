#!/usr/bin/env bash
# Control the local development Postgres.
#
#   ./db.sh start | stop | status | psql | backup | logs
#
# The cluster lives in ~/pgdata/poetry-hummus (outside /tmp, so it survives
# a reboot) and listens on 5433 to avoid clashing with any default install.
set -euo pipefail

PGBIN="${PGBIN:-/opt/homebrew/opt/postgresql@16/bin}"
PGDATA="${PGDATA:-$HOME/pgdata/poetry-hummus}"
PGPORT="${PGPORT:-5433}"
PGUSER="${PGUSER:-poet}"
PGDATABASE="${PGDATABASE:-poetry_hummus}"
LOGFILE="$HOME/pgdata/poetry-hummus.log"
BACKUPS="$HOME/pgdata/backups"

[ -x "$PGBIN/pg_ctl" ] || { echo "Postgres not found at $PGBIN" >&2; exit 1; }

case "${1:-status}" in
  start)
    if "$PGBIN/pg_isready" -h localhost -p "$PGPORT" -U "$PGUSER" >/dev/null 2>&1; then
      echo "already running on port $PGPORT"
    else
      "$PGBIN/pg_ctl" -D "$PGDATA" -o "-p $PGPORT -k /tmp" -l "$LOGFILE" start >/dev/null
      for _ in $(seq 1 20); do
        "$PGBIN/pg_isready" -h localhost -p "$PGPORT" -U "$PGUSER" >/dev/null 2>&1 && break
        sleep 1
      done
      echo "started on port $PGPORT"
    fi
    ;;
  stop)
    "$PGBIN/pg_ctl" -D "$PGDATA" -m fast stop >/dev/null && echo "stopped"
    ;;
  status)
    "$PGBIN/pg_ctl" -D "$PGDATA" status || true
    ;;
  psql)
    shift
    exec "$PGBIN/psql" -h localhost -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" "$@"
    ;;
  backup)
    mkdir -p "$BACKUPS"
    out="$BACKUPS/${PGDATABASE}-$(date +%Y%m%d-%H%M%S).dump"
    "$PGBIN/pg_dump" -h localhost -p "$PGPORT" -U "$PGUSER" -Fc -d "$PGDATABASE" -f "$out"
    echo "$out"
    ;;
  logs)
    tail -n "${2:-40}" "$LOGFILE"
    ;;
  *)
    sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac
