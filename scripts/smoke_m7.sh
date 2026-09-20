#!/usr/bin/env bash
# M7 trust smoke (Linux)
set -euo pipefail
BASE="${API_BASE:-http://127.0.0.1:8000}"
PHONE="13800138301"

json() {
  local method="$1" url="$2" body="${3:-}" token="${4:-}"
  local args=(-sS -X "$method" "$url" -H "Content-Type: application/json")
  [[ -n "$token" ]] && args+=(-H "Authorization: Bearer $token")
  [[ -n "$body" ]] && args+=(-d "$body")
  curl "${args[@]}"
}
py() { python3 -c "$1"; }

echo "== login =="
json POST "$BASE/api/v1/auth/sms/send" "{\"phone\":\"$PHONE\"}" >/dev/null
LOGIN=$(json POST "$BASE/api/v1/auth/sms/login" \
  "{\"phone\":\"$PHONE\",\"code\":\"123456\",\"device_id\":\"smoke-m7\",\"platform\":\"android\"}")
TOKEN=$(echo "$LOGIN" | py "import sys,json; print(json.load(sys.stdin)['data']['tokens']['access_token'])")
USER_ID=$(echo "$LOGIN" | py "import sys,json; print(json.load(sys.stdin)['data']['user']['id'])")

echo "== me/trust =="
TRUST=$(json GET "$BASE/api/v1/me/trust" "" "$TOKEN")
echo "$TRUST" | py "import sys,json; d=json.load(sys.stdin)['data']; print(f\"level={d['level']} confidence_low={d['confidence_low']}\")"

echo "== photo verification =="
V=$(json POST "$BASE/api/v1/verifications/photo" '{"similarity":0.95,"quality_score":0.9}' "$TOKEN")
echo "$V" | py "import sys,json; print('verification=', json.load(sys.stdin)['data']['status'])"

echo "== trust event =="
json POST "$BASE/api/v1/trust/events" \
  '{"name":"profile_completed","domain":"account","value":2,"note":"smoke"}' "$TOKEN" >/dev/null

echo "== public trust =="
PUB=$(json GET "$BASE/api/v1/users/$USER_ID/trust" "" "$TOKEN")
echo "$PUB" | py "import sys,json; d=json.load(sys.stdin)['data']; assert 'badges' in d"

echo "== admin =="
ADMIN=$(json POST "$BASE/admin/v1/auth/login" '{"username":"admin","password":"Admin@123456"}')
AT=$(echo "$ADMIN" | py "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")
SCORES=$(json GET "$BASE/admin/v1/trust/scores?limit=5" "" "$AT")
echo "$SCORES" | py "import sys,json; assert 'page_info' in json.load(sys.stdin)['data']"

echo "smoke_m7 OK"
