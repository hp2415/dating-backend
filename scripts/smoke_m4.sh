#!/usr/bin/env bash
# M4 commerce smoke (Linux)
set -euo pipefail
BASE="${API_BASE:-http://127.0.0.1:8000}"
PHONE="13800138099"

json() {
  local method="$1" url="$2" body="${3:-}" token="${4:-}" idem="${5:-}"
  local args=(-sS -X "$method" "$url" -H "Content-Type: application/json")
  [[ -n "$token" ]] && args+=(-H "Authorization: Bearer $token")
  [[ -n "$idem" ]] && args+=(-H "Idempotency-Key: $idem")
  [[ -n "$body" ]] && args+=(-d "$body")
  curl "${args[@]}"
}
py() { python3 -c "$1"; }

echo "== health =="
HEALTH=$(json GET "$BASE/health")
echo "$HEALTH" | py "import sys,json; d=json.load(sys.stdin)['data']; print('payment=', d.get('payment'), 'im=', d.get('im'))"

echo "== sms login =="
json POST "$BASE/api/v1/auth/sms/send" "{\"phone\":\"$PHONE\"}" >/dev/null
LOGIN=$(json POST "$BASE/api/v1/auth/sms/login" \
  "{\"phone\":\"$PHONE\",\"code\":\"123456\",\"device_id\":\"smoke-m4\",\"platform\":\"android\"}")
TOKEN=$(echo "$LOGIN" | py "import sys,json; print(json.load(sys.stdin)['data']['tokens']['access_token'])")

echo "== wallet =="
WALLET=$(json GET "$BASE/api/v1/me/wallet" "" "$TOKEN")
echo "$WALLET" | py "import sys,json; print('balance=', json.load(sys.stdin)['data']['balance_display'])"

echo "== topup stub wechat =="
TOPUP=$(json POST "$BASE/api/v1/me/wallet/topup" '{"amount_cents":1000,"method":"wechat"}' "$TOKEN" "smoke-topup-1")
echo "$TOPUP" | py "import sys,json; d=json.load(sys.stdin)['data']['order']; assert d['status']=='paid', d; print(f\"topup order={d['order_no']} status={d['status']}\")"

WALLET2=$(json GET "$BASE/api/v1/me/wallet" "" "$TOKEN")
echo "$WALLET2" | py "import sys,json; print('balance after topup=', json.load(sys.stdin)['data']['balance_display'])"

echo "== membership subscribe wallet =="
SUB=$(json POST "$BASE/api/v1/membership/subscribe" '{"plan_code":"monthly","method":"wallet"}' "$TOKEN" "smoke-vip-1")
echo "$SUB" | py "import sys,json; d=json.load(sys.stdin)['data']; assert d['order']['status']=='paid'; print(f\"vip={d['membership']['plan_code']} expires={d['membership']['expires_at']}\")"

echo "== companion booking stub order =="
ORDER=$(json POST "$BASE/api/v1/orders" \
  '{"kind":"companion_booking","subject_title":"演示陪玩 1 小时","amount_cents":5000}' \
  "$TOKEN" "smoke-booking-1")
ORDER_ID=$(echo "$ORDER" | py "import sys,json; print(json.load(sys.stdin)['data']['id'])")
PAY=$(json POST "$BASE/api/v1/orders/$ORDER_ID/pay" '{"method":"wallet"}' "$TOKEN")
echo "$PAY" | py "import sys,json; d=json.load(sys.stdin)['data']['order']; assert d['status']=='paid'; print(f\"booking paid order_no={d['order_no']}\")"

echo "== refund =="
RF=$(json POST "$BASE/api/v1/refunds" \
  "{\"order_id\":\"$ORDER_ID\",\"reason\":\"行程变更\",\"detail\":\"smoke_m4\"}" "$TOKEN")
echo "$RF" | py "import sys,json; d=json.load(sys.stdin)['data']; assert d['status']=='completed', d; print(f\"refund={d['status']} amount={d['amount_display']}\")"

echo "== credentials =="
CREDS=$(json GET "$BASE/api/v1/me/credentials?limit=10" "" "$TOKEN")
echo "$CREDS" | py "import sys,json; print('credentials=', json.load(sys.stdin)['data']['page_info']['total'])"

echo "== admin orders =="
ADMIN=$(json POST "$BASE/admin/v1/auth/login" '{"username":"admin","password":"Admin@123456"}')
AT=$(echo "$ADMIN" | py "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")
AO=$(json GET "$BASE/admin/v1/orders?limit=5" "" "$AT")
echo "$AO" | py "import sys,json; assert 'page_info' in json.load(sys.stdin)['data']"

echo ""
echo "smoke_m4 OK"
