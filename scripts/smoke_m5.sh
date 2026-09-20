#!/usr/bin/env bash
# M5 messaging smoke (Linux)
set -euo pipefail
BASE="${API_BASE:-http://127.0.0.1:8000}"
PHONE_A="13800138101"
PHONE_B="13800138102"

json() {
  local method="$1" url="$2" body="${3:-}" token="${4:-}" idem="${5:-}"
  local args=(-sS -X "$method" "$url" -H "Content-Type: application/json")
  [[ -n "$token" ]] && args+=(-H "Authorization: Bearer $token")
  [[ -n "$idem" ]] && args+=(-H "Idempotency-Key: $idem")
  [[ -n "$body" ]] && args+=(-d "$body")
  curl "${args[@]}"
}
py() { python3 -c "$1"; }

login() {
  local phone="$1" device="$2"
  json POST "$BASE/api/v1/auth/sms/send" "{\"phone\":\"$phone\"}" >/dev/null
  local resp
  resp=$(json POST "$BASE/api/v1/auth/sms/login" \
    "{\"phone\":\"$phone\",\"code\":\"123456\",\"device_id\":\"$device\",\"platform\":\"android\"}")
  TOKEN=$(echo "$resp" | py "import sys,json; print(json.load(sys.stdin)['data']['tokens']['access_token'])")
  USER_ID=$(echo "$resp" | py "import sys,json; print(json.load(sys.stdin)['data']['user']['id'])")
}

echo "== health =="
HEALTH=$(json GET "$BASE/health")
echo "$HEALTH" | py "import sys,json; d=json.load(sys.stdin)['data']; assert d.get('im'); print(f\"im={d['im']} version={d.get('version')}\")"

echo "== login A/B =="
login "$PHONE_A" "smoke-m5-a"
TOKEN_A="$TOKEN"; USER_A="$USER_ID"
login "$PHONE_B" "smoke-m5-b"
TOKEN_B="$TOKEN"; USER_B="$USER_ID"
echo "A=$USER_A B=$USER_B"

echo "== public uid =="
UID_A=$(json GET "$BASE/api/v1/me/public-uid" "" "$TOKEN_A")
UID_B=$(json GET "$BASE/api/v1/me/public-uid" "" "$TOKEN_B")
PUB_A=$(echo "$UID_A" | py "import sys,json; u=json.load(sys.stdin)['data']['public_uid']; assert u; print(u)")
PUB_B=$(echo "$UID_B" | py "import sys,json; u=json.load(sys.stdin)['data']['public_uid']; assert u; print(u)")
echo "uidA=$PUB_A uidB=$PUB_B"

echo "== chat status / token =="
STATUS=$(json GET "$BASE/api/v1/chat/status")
echo "$STATUS" | py "import sys,json; assert json.load(sys.stdin)['data']['provider']=='noop'"
CT=$(json POST "$BASE/api/v1/chat/token" "{}" "$TOKEN_A")
echo "$CT" | py "import sys,json; d=json.load(sys.stdin)['data']; assert d.get('token'); print(f\"token_ready={d.get('ready')}\")"

echo "== open direct =="
DM=$(json POST "$BASE/api/v1/conversations/direct" \
  "{\"peer_user_id\":\"$USER_B\",\"preview\":\"你好，冒烟测试\"}" "$TOKEN_A")
CONV_ID=$(echo "$DM" | py "import sys,json; d=json.load(sys.stdin)['data']; assert d.get('id'); print(d['id'])")
echo "$DM" | py "import sys,json; d=json.load(sys.stdin)['data']; print(f\"direct={d['id']} kind={d['kind']}\")"

echo "== list conversations =="
LIST=$(json GET "$BASE/api/v1/conversations?limit=20" "" "$TOKEN_A")
echo "$LIST" | py "import sys,json; assert 'page_info' in json.load(sys.stdin)['data']"

echo "== friend request by uid =="
FR=$(json POST "$BASE/api/v1/friend-requests" \
  "{\"to_uid\":\"$PUB_B\",\"message\":\"加个好友\",\"source\":\"uid\"}" "$TOKEN_A")
FR_ID=$(echo "$FR" | py "import sys,json; print(json.load(sys.stdin)['data']['id'])")
INCOMING=$(json GET "$BASE/api/v1/friend-requests?direction=incoming" "" "$TOKEN_B")
echo "$INCOMING" | py "import sys,json; assert len(json.load(sys.stdin)['data']['items'])>=1"
ACCEPT=$(json POST "$BASE/api/v1/friend-requests/$FR_ID/respond" '{"action":"accept"}' "$TOKEN_B")
echo "$ACCEPT" | py "import sys,json; print('friend accept=', json.load(sys.stdin)['data']['status'])"
FRIENDS=$(json GET "$BASE/api/v1/friends" "" "$TOKEN_A")
echo "$FRIENDS" | py "import sys,json; assert len(json.load(sys.stdin)['data']['items'])>=1"

echo "== create group =="
GROUP=$(json POST "$BASE/api/v1/conversations/group" \
  "{\"title\":\"冒烟群\",\"member_ids\":[\"$USER_B\"]}" "$TOKEN_A")
echo "$GROUP" | py "import sys,json; print('group=', json.load(sys.stdin)['data']['id'])"

echo "== call =="
CALL=$(json POST "$BASE/api/v1/calls" \
  "{\"conversation_id\":\"$CONV_ID\",\"callee_id\":\"$USER_B\",\"kind\":\"voice\"}" "$TOKEN_A")
CALL_ID=$(echo "$CALL" | py "import sys,json; print(json.load(sys.stdin)['data']['id'])")
json POST "$BASE/api/v1/calls/$CALL_ID/answer" "{}" "$TOKEN_B" >/dev/null
ENDED=$(json POST "$BASE/api/v1/calls/$CALL_ID/end" "{}" "$TOKEN_A")
echo "$ENDED" | py "import sys,json; print('call status=', json.load(sys.stdin)['data']['status'])"

echo "== transfer (needs wallet balance) =="
json POST "$BASE/api/v1/me/wallet/topup" '{"amount_cents":500,"method":"wechat"}' \
  "$TOKEN_A" "smoke-m5-topup-1" >/dev/null || echo "topup skipped/failed (ok if already funded)"
XFER=$(json POST "$BASE/api/v1/transfers" \
  "{\"conversation_id\":\"$CONV_ID\",\"to_user_id\":\"$USER_B\",\"amount_cents\":100}" "$TOKEN_A")
XFER_ID=$(echo "$XFER" | py "import sys,json; print(json.load(sys.stdin)['data']['id'])")
ACC=$(json POST "$BASE/api/v1/transfers/$XFER_ID/accept" "{}" "$TOKEN_B")
echo "$ACC" | py "import sys,json; print('transfer=', json.load(sys.stdin)['data']['status'])"

echo "== lookup by uid =="
LOOKUP=$(json GET "$BASE/api/v1/users/by-uid/$PUB_B" "" "$TOKEN_A")
echo "$LOOKUP" | py "import sys,json; d=json.load(sys.stdin)['data']; assert d['id']=='$USER_B'"

echo "== admin messaging =="
ADMIN=$(json POST "$BASE/admin/v1/auth/login" '{"username":"admin","password":"Admin@123456"}')
AT=$(echo "$ADMIN" | py "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")
AC=$(json GET "$BASE/admin/v1/conversations?limit=5" "" "$AT")
echo "$AC" | py "import sys,json; assert 'page_info' in json.load(sys.stdin)['data']"
AF=$(json GET "$BASE/admin/v1/friendships?limit=5" "" "$AT")
echo "$AF" | py "import sys,json; assert 'page_info' in json.load(sys.stdin)['data']"

echo ""
echo "smoke_m5 OK"
