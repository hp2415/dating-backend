#!/usr/bin/env bash
# First-time start: network + infra (or reuse) + app.
# Cloud:  ./deploy/scripts/first-up.sh
# Local:  ./deploy/scripts/first-up.sh --local
# Reuse existing PG/Redis: ./deploy/scripts/first-up.sh --reuse-infra --postgres NAME --redis NAME
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEPLOY_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$(cd "$DEPLOY_DIR/.." && pwd)"

REUSE_INFRA=0
LOCAL=0
ENV_FILE=""
POSTGRES_CONTAINER="dating-postgres"
REDIS_CONTAINER="dating-redis"

usage() {
  cat <<'EOF'
Usage: first-up.sh [--local] [--reuse-infra] [--env-file PATH] [--postgres NAME] [--redis NAME]

  --local         Publish local ports (5432/6379/8000/8080/MinIO)
  --reuse-infra   Do not start Postgres/Redis; attach existing containers to dating-net
  --env-file      Default: /opt/dating/.env if present, else dating-backend/.env
  --postgres      Container name when reusing (default dating-postgres)
  --redis         Container name when reusing (default dating-redis)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --reuse-infra) REUSE_INFRA=1; shift ;;
    --local) LOCAL=1; shift ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --postgres) POSTGRES_CONTAINER="$2"; shift 2 ;;
    --redis) REDIS_CONTAINER="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
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
  echo "Cloud:  cp deploy/.env.example /opt/dating/.env && chmod 600 /opt/dating/.env" >&2
  echo "Local:  cp .env.example .env" >&2
  exit 1
fi

export ENV_FILE

ensure_network() {
  docker network inspect dating-net >/dev/null 2>&1 || docker network create dating-net
}

wait_healthy() {
  local name="$1"
  local n=0
  local running="false"
  local health="none"
  while [[ $n -lt 60 ]]; do
    if docker inspect "$name" >/dev/null 2>&1; then
      running="$(docker inspect --format '{{.State.Running}}' "$name")"
      health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$name")"
      if [[ "$running" == "true" && ( "$health" == "healthy" || "$health" == "none" ) ]]; then
        echo "$name is ready ($health)"
        return 0
      fi
    fi
    n=$((n + 1))
    sleep 2
  done
  echo "Timeout waiting for $name (running=$running health=$health)" >&2
  docker logs --tail 80 "$name" 2>/dev/null || true
  exit 1
}

attach_container() {
  local name="$1"
  if ! docker inspect "$name" >/dev/null 2>&1; then
    echo "Container not found: $name" >&2
    exit 1
  fi
  docker network connect dating-net "$name" 2>/dev/null || true
}

infra_cmd=(docker compose -p dating-infra -f "$DEPLOY_DIR/compose.infra.yml" --env-file "$ENV_FILE")
app_cmd=(docker compose -p dating-app -f "$DEPLOY_DIR/compose.app.yml" --env-file "$ENV_FILE")

if [[ "$LOCAL" -eq 1 ]]; then
  infra_cmd+=(-f "$DEPLOY_DIR/compose.infra.local.yml")
  app_cmd+=(-f "$DEPLOY_DIR/compose.app.local.yml")
fi

ensure_network

if [[ "$REUSE_INFRA" -eq 1 ]]; then
  echo "Reusing $POSTGRES_CONTAINER and $REDIS_CONTAINER"
  attach_container "$POSTGRES_CONTAINER"
  attach_container "$REDIS_CONTAINER"
  echo "Starting MinIO only (skip if you already use Aliyun OSS)"
  "${infra_cmd[@]}" up -d minio minio-init
else
  "${infra_cmd[@]}" up -d
  wait_healthy dating-postgres
  wait_healthy dating-redis
fi

"${app_cmd[@]}" up -d --build
wait_healthy dating-api
wait_healthy dating-nginx

if [[ "$LOCAL" -eq 1 ]]; then
  echo "Ready: API http://127.0.0.1:8000/docs   Admin http://127.0.0.1:8080/"
else
  echo "Ready: http://127.0.0.1/health  Admin http://127.0.0.1/"
fi
