#!/usr/bin/env bash
# Issue a publicly trusted HTTPS certificate for this server's IP (no domain).
# Let's Encrypt IP certificates use the shortlived profile and last about 6 days.
# Certbot renews them automatically; this script also installs a daily renew cron.
#
# Run on the server, from anywhere:
#   sudo bash deploy/scripts/enable-https-ip.sh
#   sudo PUBLIC_IP=123.56.118.242 CERTBOT_EMAIL=you@example.com bash deploy/scripts/enable-https-ip.sh
#
# Requires: port 80 reachable from the internet, dating-nginx already running
# with the TLS nginx config (it can start on a temporary self-signed cert).
set -euo pipefail

PUBLIC_IP="${PUBLIC_IP:-123.56.118.242}"
WEBROOT="${WEBROOT:-/var/www/certbot}"
LINK="/etc/letsencrypt/live/public-ip"
EMAIL="${CERTBOT_EMAIL:-}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root (sudo)." >&2
  exit 1
fi

mkdir -p "$WEBROOT/.well-known/acme-challenge" /etc/letsencrypt/live

if ! command -v certbot >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update
    apt-get install -y certbot
  else
    echo "certbot is not installed and apt-get is unavailable." >&2
    exit 1
  fi
fi

# Nginx refuses to start without a certificate. A short-lived self-signed file
# only bridges the first boot; certbot replaces it below.
if [[ ! -f "$LINK/fullchain.pem" || ! -f "$LINK/privkey.pem" ]]; then
  mkdir -p "$LINK"
  openssl req -x509 -nodes -newkey rsa:2048 -days 2 \
    -keyout "$LINK/privkey.pem" \
    -out "$LINK/fullchain.pem" \
    -subj "/CN=$PUBLIC_IP" \
    -addext "subjectAltName=IP:$PUBLIC_IP"
  echo "Wrote a temporary self-signed certificate at $LINK"
  echo "Start dating-nginx, then run this script again to replace it with Let's Encrypt."
fi

if ! docker ps --format '{{.Names}}' | grep -qx dating-nginx; then
  echo "dating-nginx is not running yet. Start the stack, then run this script again to replace the temporary certificate."
  exit 0
fi

certbot_args=(
  certonly
  --webroot
  --webroot-path "$WEBROOT"
  --preferred-profile shortlived
  --ip-address "$PUBLIC_IP"
  --agree-tos
  --non-interactive
  --keep-until-expiring
  --deploy-hook "docker exec dating-nginx nginx -s reload"
)
if [[ -n "$EMAIL" ]]; then
  certbot_args+=(--email "$EMAIL")
else
  certbot_args+=(--register-unsafely-without-email)
fi

certbot "${certbot_args[@]}"

lineage="/etc/letsencrypt/live/$PUBLIC_IP"
if [[ ! -d "$lineage" ]]; then
  echo "Expected certificate directory $lineage was not created." >&2
  exit 1
fi

# The bootstrap directory may be real files. Replace it with a symlink so
# nginx keeps reading /etc/letsencrypt/live/public-ip after each renewal.
if [[ ! -L "$LINK" ]]; then
  rm -rf "$LINK"
fi
ln -sfn "$lineage" "$LINK"

docker exec dating-nginx nginx -t
docker exec dating-nginx nginx -s reload

cron_file="/etc/cron.d/dating-certbot"
cat > "$cron_file" <<'EOF'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
# IP certificates last ~6 days. Renew twice a day; certbot no-ops until due.
17 3,15 * * * root certbot renew --quiet --deploy-hook "docker exec dating-nginx nginx -s reload"
EOF
chmod 644 "$cron_file"

echo "HTTPS is ready: https://${PUBLIC_IP}/"
echo "Certificate renews via $cron_file"
