#!/usr/bin/env bash
# M3 foundation smoke (Linux)
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

echo "== health =="
HEALTH=$(json GET "$BASE/health")
echo "$HEALTH" | py "import sys,json; d=json.load(sys.stdin); assert d['code']==0; x=d['data']; print(f\"postgres={x['postgres']['ok']} postgis={x['postgres'].get('postgis')} worker={x['worker']['ok']}\")"

echo "== admin login =="
LOGIN=$(json POST "$BASE/admin/v1/auth/login" '{"username":"admin","password":"Admin@123456"}')
TOKEN=$(echo "$LOGIN" | py "import sys,json; t=json.load(sys.stdin)['data']['access_token']; assert t; print(t)")

echo "== auth/me permissions =="
ME=$(json GET "$BASE/admin/v1/auth/me" "" "$TOKEN")
echo "$ME" | py "import sys,json; d=json.load(sys.stdin)['data']; assert d['role']=='superadmin'; assert '*' in d['permissions']"

echo "== enqueue domain event =="
EV=$(json POST "$BASE/admin/v1/ops/domain-events" \
  '{"name":"ops.ping","aggregate_kind":"ops","aggregate_id":"smoke-m3","payload":{"source":"smoke_m3.sh"}}' \
  "$TOKEN")
echo "$EV" | py "import sys,json; d=json.load(sys.stdin)['data']; print(f\"event id={d['id']} status={d['status']}\")"

echo "== list domain events (page_info) =="
LIST=$(json GET "$BASE/admin/v1/ops/domain-events?limit=5&offset=0" "" "$TOKEN")
echo "$LIST" | py "import sys,json; d=json.load(sys.stdin)['data']; assert 'page_info' in d; assert d.get('total') is not None; print(f\"total={d['total']} has_more={d['page_info']['has_more']}\")"

echo "== activities list page_info =="
ACTS=$(json GET "$BASE/admin/v1/activities?status=all&limit=5&offset=0" "" "$TOKEN")
echo "$ACTS" | py "import sys,json; assert 'page_info' in json.load(sys.stdin)['data']"

echo "== event handlers inventory =="
HANDLERS=$(json GET "$BASE/admin/v1/ops/event-handlers" "" "$TOKEN")
echo "$HANDLERS" | py "import sys,json; assert len(json.load(sys.stdin)['data']['items'])>=1"

echo ""
echo "smoke_m3 OK — wait ~15s for worker to drain ops.ping (status -> done)"
echo "Re-check: GET $BASE/admin/v1/ops/domain-events"
