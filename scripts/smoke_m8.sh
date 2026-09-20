#!/usr/bin/env bash
# M8 ops smoke (Linux)
set -euo pipefail
BASE="${API_BASE:-http://127.0.0.1:8000}"
PHONE="13800138401"

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
  "{\"phone\":\"$PHONE\",\"code\":\"123456\",\"device_id\":\"smoke-m8\",\"platform\":\"android\"}")
TOKEN=$(echo "$LOGIN" | py "import sys,json; print(json.load(sys.stdin)['data']['tokens']['access_token'])")

echo "== taxonomies =="
TAX=$(json GET "$BASE/api/v1/taxonomies?kind=activity_category" "" "$TOKEN")
echo "$TAX" | py "import sys,json; n=len(json.load(sys.stdin)['data']['items']); assert n>=1, 'taxonomies empty — run migrate/seed'; print('categories=', n)"

echo "== shelves =="
json GET "$BASE/api/v1/discover/shelves" "" "$TOKEN" >/dev/null

echo "== push token =="
json POST "$BASE/api/v1/me/push-token" \
  '{"device_id":"smoke-m8","platform":"android","token":"fake-fcm-token","provider":"fcm"}' \
  "$TOKEN" >/dev/null

echo "== feedback =="
json POST "$BASE/api/v1/feedbacks" '{"category":"general","content":"烟雾测试反馈"}' "$TOKEN" >/dev/null

echo "== admin announce =="
ADMIN=$(json POST "$BASE/admin/v1/auth/login" '{"username":"admin","password":"Admin@123456"}')
AT=$(echo "$ADMIN" | py "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")
ANN=$(json POST "$BASE/admin/v1/announcements" '{"title":"M8 烟雾公告","body":"hello"}' "$AT")
ANN_ID=$(echo "$ANN" | py "import sys,json; print(json.load(sys.stdin)['data']['id'])")
json POST "$BASE/admin/v1/announcements/$ANN_ID/publish" "{}" "$AT" >/dev/null
LIST=$(json GET "$BASE/api/v1/announcements" "" "$TOKEN")
echo "$LIST" | py "import sys,json; print('announcements=', len(json.load(sys.stdin)['data']['items']))"

echo "smoke_m8 OK"
