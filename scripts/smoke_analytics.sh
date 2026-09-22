#!/usr/bin/env bash
# Analytics ingest smoke (Linux / server).
# Batch accept, event_id dedupe, unknown names stored, >50 rejected, 60/min rate limit.
# Usage: API_BASE=http://127.0.0.1:8000 ./scripts/smoke_analytics.sh
set -euo pipefail
BASE="${API_BASE:-http://127.0.0.1:8000}"

RESP_STATUS=""
RESP_BODY=""

call() {
  local method="$1" url="$2" body="${3:-}"
  local tmp
  tmp=$(mktemp)
  if [[ -n "$body" ]]; then
    RESP_STATUS=$(curl -sS -o "$tmp" -w "%{http_code}" -X "$method" "$url" \
      -H "Content-Type: application/json" --data-binary "$body")
  else
    RESP_STATUS=$(curl -sS -o "$tmp" -w "%{http_code}" -X "$method" "$url")
  fi
  RESP_BODY=$(cat "$tmp")
  rm -f "$tmp"
}

assert_json() {
  printf '%s' "$RESP_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); $1"
}

# make_batch ANON ID NAME [ID NAME ...]
make_batch() {
  python3 - "$@" <<'PY'
import datetime, json, sys
anon = sys.argv[1]
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
events = []
args = sys.argv[2:]
for i in range(0, len(args), 2):
    events.append({
        "event_id": args[i],
        "event_name": args[i + 1],
        "anon_id": anon,
        "session_id": "smoke-session",
        "screen": "smoke",
        "props": {"cold_start": "true"},
        "occurred_at": now,
        "platform": "android",
        "app_version": "smoke",
        "build_type": "debug",
        "os_version": "test",
        "device_model": "script",
        "network_type": "wifi",
    })
print(json.dumps({"events": events}, ensure_ascii=False))
PY
}

# make_n ANON COUNT NAME
make_n() {
  python3 - "$@" <<'PY'
import datetime, json, sys, uuid
anon, count, name = sys.argv[1], int(sys.argv[2]), sys.argv[3]
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
events = []
for _ in range(count):
    events.append({
        "event_id": str(uuid.uuid4()),
        "event_name": name,
        "anon_id": anon,
        "session_id": "smoke-session",
        "screen": "smoke",
        "props": {"cold_start": "true"},
        "occurred_at": now,
        "platform": "android",
        "app_version": "smoke",
        "build_type": "debug",
        "os_version": "test",
        "device_model": "script",
        "network_type": "wifi",
    })
print(json.dumps({"events": events}, ensure_ascii=False))
PY
}

uuid() { python3 -c 'import uuid; print(uuid.uuid4())'; }

echo "== health =="
call GET "$BASE/health"
if [[ "$RESP_STATUS" != "200" ]]; then
  echo "health failed: HTTP $RESP_STATUS $RESP_BODY" >&2
  exit 1
fi
assert_json "assert d['code']==0"

ID1=$(uuid)
ID2=$(uuid)
ANON="smoke-$(uuid)"

echo "== accept batch =="
call POST "$BASE/api/v1/analytics/events" "$(make_batch "$ANON" "$ID1" "app.launched" "$ID2" "auth.login_viewed")"
if [[ "$RESP_STATUS" != "200" ]]; then
  echo "ingest failed: HTTP $RESP_STATUS $RESP_BODY" >&2
  exit 1
fi
assert_json "assert d['code']==0; assert d['data']['accepted']==2; assert d['data']['duplicated']==0, d"

echo "== dedupe =="
call POST "$BASE/api/v1/analytics/events" "$(make_batch "$ANON" "$ID1" "app.launched" "$ID2" "auth.login_viewed")"
if [[ "$RESP_STATUS" != "200" ]]; then
  echo "dedupe ingest failed: HTTP $RESP_STATUS $RESP_BODY" >&2
  exit 1
fi
assert_json "assert d['code']==0; assert d['data']['accepted']==0; assert d['data']['duplicated']==2, d"

echo "== unknown event still accepted =="
UNKNOWN_ID=$(uuid)
call POST "$BASE/api/v1/analytics/events" "$(make_batch "$ANON" "$UNKNOWN_ID" "smoke.unknown_event")"
assert_json "assert d['code']==0 and d['data']['accepted']==1, d"

echo "== batch over 50 rejected =="
call POST "$BASE/api/v1/analytics/events" "$(make_n "$ANON" 51 "app.launched")"
if [[ "$RESP_STATUS" != "422" ]]; then
  echo "expected 422 validation, got HTTP $RESP_STATUS $RESP_BODY" >&2
  exit 1
fi
assert_json "assert d['code']==90002, d"

echo "== rate limit =="
limited=0
for i in $(seq 1 70); do
  call POST "$BASE/api/v1/analytics/events" "$(make_n "$ANON" 1 "app.launched")"
  code=$(printf '%s' "$RESP_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('code',''))" || true)
  if [[ "$RESP_STATUS" == "429" && "$code" == "10004" ]]; then
    limited=1
    echo "limited after $i extra requests in this loop"
    break
  fi
  if [[ "$code" != "0" ]]; then
    echo "unexpected during rate loop: HTTP $RESP_STATUS $RESP_BODY" >&2
    exit 1
  fi
done
if [[ "$limited" != "1" ]]; then
  echo "rate limit did not trip within 70 requests" >&2
  exit 1
fi

echo ""
echo "smoke_analytics OK"
