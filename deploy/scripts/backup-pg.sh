#!/usr/bin/env bash
# Dump Postgres to /opt/dating/backups (or BACKUP_DIR). Does not stop containers.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

ENV_FILE=""
CONTAINER="dating-postgres"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --container) CONTAINER="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: backup-pg.sh [--env-file PATH] [--container NAME]"
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$ENV_FILE" ]]; then
  if [[ -f /opt/dating/.env ]]; then
    ENV_FILE=/opt/dating/.env
  elif [[ -f "$BACKEND_DIR/.env" ]]; then
    ENV_FILE="$BACKEND_DIR/.env"
  fi
fi

env_get() {
  local key="$1"
  local fallback="$2"
  if [[ -z "${ENV_FILE:-}" || ! -f "$ENV_FILE" ]]; then
    echo "$fallback"
    return
  fi
  local line
  line="$(grep -E "^${key}=" "$ENV_FILE" | tail -1 || true)"
  if [[ -z "$line" ]]; then
    echo "$fallback"
    return
  fi
  echo "${line#*=}" | tr -d '\r'
}

PGUSER="$(env_get POSTGRES_USER dating)"
PGDB="$(env_get POSTGRES_DB dating)"
BACKUP_DIR="${BACKUP_DIR:-/opt/dating/backups}"

mkdir -p "$BACKUP_DIR"
OUT="$BACKUP_DIR/dating-$(date +%Y%m%d-%H%M%S).dump"

docker exec "$CONTAINER" pg_dump -U "$PGUSER" -d "$PGDB" -Fc > "$OUT"
echo "Wrote $OUT"
