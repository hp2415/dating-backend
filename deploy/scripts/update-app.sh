#!/usr/bin/env bash
# Rebuild API / worker / admin / nginx only. Never touches Postgres or Redis volumes.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEPLOY_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$(cd "$DEPLOY_DIR/.." && pwd)"

LOCAL=0
ENV_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --local) LOCAL=1; shift ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: update-app.sh [--local] [--env-file PATH]"
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$ENV_FILE" ]]; then
  if [[ -f /opt/dating/.env ]]; then
    ENV_FILE=/opt/dating/.env
  else
    ENV_FILE="$BACKEND_DIR/.env"
  fi
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE" >&2
  exit 1
fi

export ENV_FILE

app_cmd=(docker compose -p dating-app -f "$DEPLOY_DIR/compose.app.yml" --env-file "$ENV_FILE")
if [[ "$LOCAL" -eq 1 ]]; then
  app_cmd+=(-f "$DEPLOY_DIR/compose.app.local.yml")
fi

"${app_cmd[@]}" up -d --build
echo "App stack updated. Infra was not restarted."
