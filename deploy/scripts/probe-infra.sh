#!/usr/bin/env bash
# Inspect existing Postgres / Redis containers. Does not delete anything.
set -euo pipefail

echo "=== docker ps -a (postgres / redis / minio) ==="
docker ps -a --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}" \
  | awk 'NR==1 || /postgres|redis|minio|dating/ {print}'

echo
echo "=== probe named containers (ignore errors if a name does not exist) ==="
for name in dating-postgres postgres pg pgsql postgresql; do
  if docker inspect "$name" >/dev/null 2>&1; then
    echo "-- $name pg_isready --"
    docker exec "$name" pg_isready || true
    echo "-- $name env / mounts / ports --"
    docker inspect "$name" --format 'image={{.Config.Image}}
running={{.State.Running}} status={{.State.Status}}
ports={{json .NetworkSettings.Ports}}
networks={{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}
mounts={{range .Mounts}}{{.Destination}} <- {{.Name}}{{.Source}}; {{end}}
env={{range .Config.Env}}{{println .}}{{end}}'
    break
  fi
done

for name in dating-redis redis; do
  if docker inspect "$name" >/dev/null 2>&1; then
    echo "-- $name redis-cli ping --"
    docker exec "$name" redis-cli ping || true
    echo "-- $name image={{.Config.Image}} mounts --"
    docker inspect "$name" --format 'image={{.Config.Image}}
ports={{json .NetworkSettings.Ports}}
networks={{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}
mounts={{range .Mounts}}{{.Destination}} <- {{.Name}}{{.Source}}; {{end}}'
    break
  fi
done

echo
echo "Decision:"
echo "  Healthy + named volume + known password -> first-up.sh --reuse-infra --postgres NAME --redis NAME"
echo "  Missing / exited / no volume            -> first-up.sh  (creates compose.infra.yml)"
echo "  0.0.0.0:5432 or 6379                    -> close those ports in the cloud security group"
