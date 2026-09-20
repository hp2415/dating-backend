#!/usr/bin/env bash
# B-class APIs smoke: settings, public user, activity fee/details/favorite/search, community bookmark
# Usage: API_BASE=http://127.0.0.1:8000 ./scripts/smoke_b_class.sh
set -euo pipefail
BASE="${API_BASE:-http://127.0.0.1:8000}"

json() {
  local method="$1" url="$2" body="${3:-}" token="${4:-}"
  local args=(-sS -X "$method" "$url" -H "Content-Type: application/json")
  [[ -n "$token" ]] && args+=(-H "Authorization: Bearer $token")
  [[ -n "$body" ]] && args+=(-d "$body")
  curl "${args[@]}"
}
py() { python3 -c "$1"; }
jget() {
  local payload="$1" expr="$2"
  printf '%s' "$payload" | py "import sys,json; d=json.load(sys.stdin); $expr"
}

echo "== login =="
LOGIN=$(json POST "$BASE/api/v1/auth/sms/login" \
  '{"phone":"13900009902","code":"123456","device_id":"smoke-b-class","platform":"android"}')
TOKEN=$(jget "$LOGIN" "t=d['data']['tokens']['access_token']; assert t; print(t)")
USER_ID=$(jget "$LOGIN" "print(d['data']['user']['id'])")

echo "== me/settings =="
SET=$(json GET "$BASE/api/v1/me/settings" "" "$TOKEN")
jget "$SET" "assert d['code']==0; assert 'youth_mode' in d['data']"
SET2=$(json PUT "$BASE/api/v1/me/settings" '{"youth_mode":false,"notify_message":true}' "$TOKEN")
jget "$SET2" "assert d['data']['notify_message'] is True"

echo "== users/{id} =="
PUB=$(json GET "$BASE/api/v1/users/$USER_ID" "" "$TOKEN")
jget "$PUB" "assert d['code']==0; assert 'trust' in d['data']; assert 'badges' in d['data']['trust']"

echo "== create activity with fee =="
# Need completed profile — soft-complete for smoke
json PUT "$BASE/api/v1/me/profile" \
  '{"display_name":"BClassSmoke","birthday":"1995-01-01","gender":"male","city":"上海"}' \
  "$TOKEN" >/dev/null
ACT=$(json POST "$BASE/api/v1/activities" \
  '{"title":"B-class 徒步","description":"smoke","category":"outdoors","city":"上海","capacity":8,"fee_type":"online_pay","fee_cents":12000,"fee_note":"含保险"}' \
  "$TOKEN")
ACT_ID=$(jget "$ACT" "assert d['code']==0; assert d['data']['fee_type']=='online_pay'; assert d['data']['fee_cents']==12000; print(d['data']['id'])")
echo "activity=$ACT_ID"

echo "== details upsert =="
DET=$(json PUT "$BASE/api/v1/activities/$ACT_ID/details" \
  '{"timeline":[{"time":"09:00","title":"集合"}],"host_note":"带水"}' \
  "$TOKEN")
jget "$DET" "assert d['data']['host_note']=='带水'; assert len(d['data']['timeline'])==1"

echo "== search =="
# pending activities won't show in search — ok, just ensure endpoint works
SEARCH=$(json GET "$BASE/api/v1/activities/search?q=B-class&limit=5" "" "$TOKEN")
jget "$SEARCH" "assert d['code']==0; assert 'items' in d['data']"

echo "== community library endpoints =="
for kind in bookmarks liked posts reposts; do
  LIB=$(json GET "$BASE/api/v1/me/community/$kind?limit=5" "" "$TOKEN")
  jget "$LIB" "assert d['code']==0; assert 'items' in d['data']"
done

echo ""
echo "smoke_b_class OK (favorite/bookmark need published content — covered by unit paths)"
