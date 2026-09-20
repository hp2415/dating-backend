#!/usr/bin/env bash
# M6 companion / buddy smoke (Linux). Usage:
#   API_BASE=http://127.0.0.1:8000 bash scripts/smoke_m6.sh
set -euo pipefail
BASE="${API_BASE:-http://127.0.0.1:8000}"
PHONE_A="13800138201"
PHONE_B="13800138202"

json() {
  local method="$1" url="$2" body="${3:-}" token="${4:-}" idem="${5:-}"
  local args=(-sS -X "$method" "$url" -H "Content-Type: application/json")
  if [[ -n "$token" ]]; then args+=(-H "Authorization: Bearer $token"); fi
  if [[ -n "$idem" ]]; then args+=(-H "Idempotency-Key: $idem"); fi
  if [[ -n "$body" ]]; then args+=(-d "$body"); fi
  curl "${args[@]}"
}

py() { python3 -c "$1"; }

login() {
  local phone="$1" device="$2"
  json POST "$BASE/api/v1/auth/sms/send" "{\"phone\":\"$phone\"}" >/dev/null
  local resp
  resp=$(json POST "$BASE/api/v1/auth/sms/login" \
    "{\"phone\":\"$phone\",\"code\":\"123456\",\"device_id\":\"$device\",\"platform\":\"android\"}")
  TOKEN=$(echo "$resp" | py "import sys,json; d=json.load(sys.stdin); print(d['data']['tokens']['access_token'])")
  USER_ID=$(echo "$resp" | py "import sys,json; d=json.load(sys.stdin); print(d['data']['user']['id'])")
}

echo "== login =="
login "$PHONE_A" "smoke-m6-a"
TOKEN_A="$TOKEN"; USER_A="$USER_ID"
login "$PHONE_B" "smoke-m6-b"
TOKEN_B="$TOKEN"; USER_B="$USER_ID"
echo "A=$USER_A B=$USER_B"

echo "== buddy intent =="
json PUT "$BASE/api/v1/me/buddy-intent" \
  '{"text":"找周末爬山搭子","tags":["hiking"],"city":"上海","active":true}' \
  "$TOKEN_A" >/dev/null
FEED=$(json GET "$BASE/api/v1/buddies/feed?limit=10" "" "$TOKEN_B")
echo "$FEED" | py "import sys,json; d=json.load(sys.stdin); print('feed total=', d['data']['page_info']['total'])"

echo "== greet =="
json POST "$BASE/api/v1/buddies/$USER_A/greet" '{"text":"你好呀"}' "$TOKEN_B" >/dev/null

echo "== companion apply + admin approve =="
json POST "$BASE/api/v1/companions/apply" \
  '{"service_type":"offline","specialty":"户外向导","intro":"烟雾测试陪玩","city":"上海"}' \
  "$TOKEN_A" >/dev/null
ADMIN=$(json POST "$BASE/admin/v1/auth/login" '{"username":"admin","password":"Admin@123456"}')
ADMIN_TOKEN=$(echo "$ADMIN" | py "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")
json POST "$BASE/admin/v1/companions/$USER_A/review" '{"action":"approve"}' "$ADMIN_TOKEN" >/dev/null

echo "== service + slot =="
SVC=$(json POST "$BASE/api/v1/me/companion-profile/services" \
  '{"title":"半日徒步","pricing_unit":"session","price_cents":19900,"min_units":1}' \
  "$TOKEN_A")
SVC_ID=$(echo "$SVC" | py "import sys,json; print(json.load(sys.stdin)['data']['id'])")
START=$(py "from datetime import datetime,timedelta,timezone; print((datetime.now(timezone.utc)+timedelta(days=2)).isoformat())")
END=$(py "from datetime import datetime,timedelta,timezone; print((datetime.now(timezone.utc)+timedelta(days=2,hours=3)).isoformat())")
SLOT=$(json POST "$BASE/api/v1/me/companion-profile/slots" \
  "{\"start_at\":\"$START\",\"end_at\":\"$END\"}" \
  "$TOKEN_A")
SLOT_ID=$(echo "$SLOT" | py "import sys,json; print(json.load(sys.stdin)['data']['id'])")

echo "== booking =="
BOOKING=$(json POST "$BASE/api/v1/bookings" \
  "{\"companion_id\":\"$USER_A\",\"service_id\":\"$SVC_ID\",\"slot_id\":\"$SLOT_ID\",\"units\":1}" \
  "$TOKEN_B" "smoke-m6-booking-1")
ORDER_ID=$(echo "$BOOKING" | py "import sys,json; print(json.load(sys.stdin)['data']['order']['id'])")
BOOKING_ID=$(echo "$BOOKING" | py "import sys,json; print(json.load(sys.stdin)['data']['id'])")
PAY=$(json POST "$BASE/api/v1/orders/$ORDER_ID/pay" '{"method":"wallet"}' "$TOKEN_B")
echo "$PAY" | py "import sys,json; d=json.load(sys.stdin); assert d['data']['order']['status']=='paid', d"
json POST "$BASE/api/v1/bookings/$BOOKING_ID/start" "{}" "$TOKEN_A" >/dev/null
json POST "$BASE/api/v1/bookings/$BOOKING_ID/complete" "{}" "$TOKEN_A" >/dev/null

echo "== leaderboard =="
LB=$(json GET "$BASE/api/v1/companions/leaderboard?period=week" "" "$TOKEN_B")
echo "$LB" | py "import sys,json; print('leaderboard items=', len(json.load(sys.stdin)['data']['items']))"

echo ""
echo "smoke_m6 OK"
