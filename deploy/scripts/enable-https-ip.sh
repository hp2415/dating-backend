#!/usr/bin/env bash
# Issue a publicly trusted HTTPS certificate for this server's IP (no domain).
# Let's Encrypt IP certificates use the shortlived profile and last about 6 days.
#
# Certbot runs in Docker, so the host does not need apt/yum or a system certbot.
# Aliyun images are often Alibaba Cloud Linux (dnf/yum), not Debian.
#
#   sudo bash deploy/scripts/enable-https-ip.sh
#   sudo PUBLIC_IP=123.56.118.242 CERTBOT_EMAIL=you@example.com bash deploy/scripts/enable-https-ip.sh
#
# Requires port 80 reachable from the internet, and dating-nginx running with
# deploy/nginx/dating.conf (it may boot on the temporary self-signed cert).
set -euo pipefail

PUBLIC_IP="${PUBLIC_IP:-123.56.118.242}"
WEBROOT="${WEBROOT:-/var/www/certbot}"
LINK="/etc/letsencrypt/live/public-ip"
EMAIL="${CERTBOT_EMAIL:-}"
CERTBOT_IMAGE="${CERTBOT_IMAGE:-docker.m.daocloud.io/certbot/certbot:latest}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root (sudo)." >&2
  exit 1
fi

mkdir -p "$WEBROOT/.well-known/acme-challenge" /etc/letsencrypt/live

write_bootstrap_cert() {
  local cnf
  cnf="$(mktemp)"
  cat > "$cnf" <<EOF
[req]
distinguished_name = req_dn
x509_extensions = v3_req
prompt = no
[req_dn]
CN = ${PUBLIC_IP}
[v3_req]
subjectAltName = IP:${PUBLIC_IP}
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
EOF
  mkdir -p "$LINK"
  openssl req -x509 -nodes -newkey rsa:2048 -days 2 \
    -keyout "$LINK/privkey.pem" \
    -out "$LINK/fullchain.pem" \
    -config "$cnf"
  rm -f "$cnf"
}

if [[ ! -f "$LINK/fullchain.pem" || ! -f "$LINK/privkey.pem" ]]; then
  write_bootstrap_cert
  echo "Wrote a temporary self-signed certificate at $LINK"
fi

if ! docker ps --format '{{.Names}}' | grep -qx dating-nginx; then
  echo "dating-nginx is not running yet."
  echo "Start the stack, then run this script again:"
  echo "  docker compose -p dating-app -f deploy/compose.app.yml --env-file ./.env up -d"
  exit 0
fi

echo "Pulling $CERTBOT_IMAGE"
if ! docker pull "$CERTBOT_IMAGE"; then
  echo "Mirror pull failed, trying certbot/certbot:latest"
  CERTBOT_IMAGE="certbot/certbot:latest"
  docker pull "$CERTBOT_IMAGE"
fi

certbot_args=(
  certonly
  --webroot
  --webroot-path /var/www/certbot
  --preferred-profile shortlived
  --ip-address "$PUBLIC_IP"
  --agree-tos
  --non-interactive
  --keep-until-expiring
)
if [[ -n "$EMAIL" ]]; then
  certbot_args+=(--email "$EMAIL")
else
  certbot_args+=(--register-unsafely-without-email)
fi

# --network host: the bridge DNS on this ECS cannot resolve
# acme-v02.api.letsencrypt.org. Host network uses the host resolver.
# The image entrypoint is already certbot. Do not pass a deploy-hook here:
# it would run inside the container, which cannot see the host Docker socket.
docker run --rm --network host \
  -v /etc/letsencrypt:/etc/letsencrypt \
  -v /var/www/certbot:/var/www/certbot \
  "$CERTBOT_IMAGE" \
  "${certbot_args[@]}"

lineage="/etc/letsencrypt/live/$PUBLIC_IP"
if [[ ! -d "$lineage" ]]; then
  echo "Expected certificate directory $lineage was not created." >&2
  exit 1
fi

if [[ ! -L "$LINK" ]]; then
  rm -rf "$LINK"
fi
ln -sfn "$lineage" "$LINK"

docker exec dating-nginx nginx -t
docker exec dating-nginx nginx -s reload

cron_file="/etc/cron.d/dating-certbot"
cat > "$cron_file" <<EOF
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
# IP certificates last about 6 days. certbot renew does nothing until due.
17 3,15 * * * root docker run --rm --network host -v /etc/letsencrypt:/etc/letsencrypt -v ${WEBROOT}:/var/www/certbot ${CERTBOT_IMAGE} renew --quiet && docker exec dating-nginx nginx -s reload
EOF
chmod 644 "$cron_file"

echo "HTTPS is ready: https://${PUBLIC_IP}/"
echo "Certificate renews via $cron_file"
