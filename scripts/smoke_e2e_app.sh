#!/usr/bin/env bash
# End-to-end app smoke (W4-3): login -> profile -> activity -> post -> wallet topup
# Requires local/staging API with SMS_ALLOW_DEV_CODE and seed admin.
# Usage:
#   ./scripts/smoke_e2e_app.sh
#   API_BASE=http://123.56.118.242 ./scripts/smoke_e2e_app.sh
set -euo pipefail
BASE="${API_BASE:-http://127.0.0.1:8000}"
BASE="${BASE%/}"

json() {
  local method="$1" url="$2" body="${3:-}" token="${4:-}" extra_hdr="${5:-}"
  local args=(-sS -X "$method" "$url" -H "Content-Type: application/json")
  [[ -n "$token" ]] && args+=(-H "Authorization: Bearer $token")
  [[ -n "$extra_hdr" ]] && args+=(-H "$extra_hdr")
  [[ -n "$body" ]] && args+=(-d "$body")
  curl "${args[@]}"
}

py() { python3 -c "$1"; }

jget() {
  local payload="$1" expr="$2"
  printf '%s' "$payload" | py "import sys,json; d=json.load(sys.stdin); $expr"
}

login() {
  local phone="$1"
  json POST "$BASE/api/v1/auth/sms/send" "{\"phone\":\"$phone\"}" >/dev/null 2>&1 || true
  local resp
  resp=$(json POST "$BASE/api/v1/auth/sms/login" \
    "{\"phone\":\"$phone\",\"code\":\"123456\",\"device_id\":\"e2e-smoke\",\"platform\":\"android\"}")
  jget "$resp" "t=d['data']['tokens']['access_token']; assert t; print(t)"
}

admin_token() {
  local resp
  resp=$(json POST "$BASE/admin/v1/auth/login" \
    '{"username":"admin","password":"Admin@123456"}')
  jget "$resp" "t=d['data']['access_token']; assert t; print(t)"
}

# HHmmss is 6 digits; pad to 11-digit CN mobile without bash octal (08xxxx).
SUFFIX=$(date +%H%M%S)
PHONE_A="13600${SUFFIX}"
PHONE_B="13700${SUFFIX}"

echo "== base=$BASE =="
echo "== login A/B phoneA=$PHONE_A =="
TOKEN_A=$(login "$PHONE_A")
TOKEN_B=$(login "$PHONE_B")

echo "== profiles =="
json PUT "$BASE/api/v1/me/profile" \
  '{"display_name":"E2E-A","birthday":"1998-01-01","gender":"female","city":"Shanghai","bio":"e2e","tags":["sport"]}' \
  "$TOKEN_A" >/dev/null
json PUT "$BASE/api/v1/me/profile" \
  '{"display_name":"E2E-B","birthday":"1997-01-01","gender":"male","city":"Shanghai","bio":"e2e","tags":["food"]}' \
  "$TOKEN_B" >/dev/null

echo "== create + approve activity =="
ACT=$(json POST "$BASE/api/v1/activities" \
  '{"title":"E2E weekend hike","description":"e2e","category":"outdoors","city":"Shanghai","capacity":6,"media":[]}' \
  "$TOKEN_A")
AID=$(jget "$ACT" "print(d['data']['id'])")
ADMIN=$(admin_token)
json POST "$BASE/admin/v1/activities/$AID/review" '{"action":"approve"}' "$ADMIN" >/dev/null
json POST "$BASE/api/v1/activities/$AID/join" '{}' "$TOKEN_B" >/dev/null

echo "== create + approve post =="
POST=$(json POST "$BASE/api/v1/community/posts" \
  '{"content":"E2E post hello","media":[]}' \
  "$TOKEN_B")
PID=$(jget "$POST" "print(d['data']['id'])")
json POST "$BASE/admin/v1/community/posts/$PID/review" '{"action":"approve"}' "$ADMIN" >/dev/null

echo "== wallet topup stub =="
IDEM=$(py "import uuid; print(uuid.uuid4())")
json POST "$BASE/api/v1/me/wallet/topup" \
  '{"amount_cents":10000,"method":"wechat"}' \
  "$TOKEN_A" \
  "Idempotency-Key: $IDEM" >/dev/null
WALLET=$(json GET "$BASE/api/v1/me/wallet" "" "$TOKEN_A")
jget "$WALLET" "
bal=int(d['data']['balance_cents'])
print(f'wallet_balance={bal}')
assert bal>=10000, 'expected topup credited'
"

echo "== admin user lookup =="
# Needs backend >= 0.9.2 (admin users router). Rebuild if this 404s.
USERS=$(curl -sS -G "$BASE/admin/v1/users" \
  --data-urlencode "q=$PHONE_A" \
  --data-urlencode "limit=5" \
  -H "Authorization: Bearer $ADMIN" \
  -H "Content-Type: application/json")
jget "$USERS" "
if d.get('detail') is not None or d.get('code') not in (0, None):
    raise AssertionError('admin /users unavailable or failed (rebuild API?): ' + str(d)[:400])
assert d.get('code') == 0, 'admin /users failed: ' + str(d)[:400]
items = (d.get('data') or {}).get('items') or []
assert len(items) >= 1, 'admin users should find phoneA; response=' + str(d)[:400]
print(f\"admin_users_hit={len(items)} id={items[0].get('id')}\")
"

echo "E2E_APP SMOKE OK activity=$AID post=$PID"
