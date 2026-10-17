import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

pytestmark = pytest.mark.asyncio


def _ev(name, anon, session, *, at, **kw):
    return {"event_id": str(uuid4()), "event_name": name, "anon_id": anon, "session_id": session,
            "occurred_at": at.isoformat(), "app_version": "9.9.9", "platform": "android", **kw}


async def _admin_login(client, super_headers, role):
    username = f"t_{role}_{uuid4().hex[:6]}"
    r = await client.post("/admin/v1/admins", headers=super_headers,
                          json={"username": username, "password": "Passw0rd!x1", "role": role, "display_name": role})
    assert r.json()["code"] == 0, r.text
    r = await client.post("/admin/v1/auth/login", json={"username": username, "password": "Passw0rd!x1"})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


async def test_analytics_end_to_end(client, make_user, admin_headers):
    user = await make_user("埋点用户")
    anon = f"anon-{uuid4().hex[:10]}"
    sess = f"sess-{uuid4().hex[:8]}"
    obj = str(uuid4())
    now = datetime.now(timezone.utc)
    # device clock is 1h behind the server
    skew = timedelta(hours=1)
    sent_at = now - skew

    def at(seconds_ago):
        return sent_at - timedelta(seconds=seconds_ago)

    dup = _ev("page.viewed", anon, sess, at=at(60), screen="activities")
    events = [
        dup,
        dup,
        _ev("item.exposed", anon, sess, at=at(50), screen="activities", object_type="activity", object_id=obj,
            props={"list_id": "feed", "position": 2}),
        _ev("item.clicked", anon, sess, at=at(45), screen="activities", object_type="activity", object_id=obj),
        _ev("activity.detail_viewed", anon, sess, at=at(40), object_id=obj),
        _ev("activity.join_clicked", anon, sess, at=at(30), object_id=obj),
        _ev("activity.join_succeeded", anon, sess, at=at(25), object_id=obj),
        _ev("commerce.pay_succeeded", anon, sess, at=at(20), object_type="activity", object_id=obj,
            props={"method": "wechat", "amount_cents": 1000, "phone": "13800138000", "note": "call 13800138000"}),
        _ev("perf.cold_start", anon, sess, at=at(55), duration_ms=900),
        _ev("perf.cold_start", anon, sess, at=at(54), duration_ms=1500),
        _ev("error.api_failed", anon, sess, at=at(10), props={"path": "/api/v1/x", "status": 500}),
        _ev("Bad Name!", anon, sess, at=at(10)),
        _ev("page.left", anon, sess, at=now - timedelta(days=30) - skew),  # too old (relative to sent_at → corrected age 30d)
    ]
    # the too-old event: age = sent_at - occurred_at = 30d
    events[-1]["occurred_at"] = (sent_at - timedelta(days=30)).isoformat()
    body = {"schema_version": 2, "sdk_version": "1.0", "sent_at": sent_at.isoformat(), "events": events}

    r = await client.post("/api/v1/analytics/events", json=body, headers=user["h"])
    d = r.json()["data"]
    assert d["accepted"] == 10 and d["duplicated"] == 1, d
    reasons = {x["reason"] for x in d["rejected"]}
    assert reasons == {"bad_event_name", "too_old"}
    assert d["sanitized_props"] >= 1 and d["config"]["enabled"] is True
    r2 = await client.post("/api/v1/analytics/events", json=body, headers=user["h"])
    assert r2.json()["data"]["accepted"] == 0 and r2.json()["data"]["duplicated"] == 11

    r = await client.post("/api/v1/analytics/events", json={"schema_version": 7, "events": events[:1]})
    assert r.json()["code"] != 0

    # aggregation
    rb = await client.post("/admin/v1/analytics/rebuild?days=1", headers=admin_headers)
    assert rb.json()["code"] == 0, rb.text
    ov = (await client.get("/admin/v1/analytics/overview?days=2", headers=admin_headers)).json()["data"]
    assert ov["latest"]["dau"] >= 1 and ov["latest"]["sessions"] >= 1
    objs = (await client.get("/admin/v1/analytics/objects?object_type=activity", headers=admin_headers)).json()["data"]
    row = next(i for i in objs["items"] if i["object_id"] == obj)
    assert row["exposures"] == 1 and row["clicks"] == 1 and row["details"] == 1 and row["conversions"] == 1 and row["paid"] == 1
    assert row["ctr"] == 1.0
    fn = (await client.get("/admin/v1/analytics/funnel?name=activity_join", headers=admin_headers)).json()["data"]
    assert fn["steps"][0]["users"] >= 1 and fn["steps"][-1]["users"] >= 1
    perf = (await client.get("/admin/v1/analytics/perf", headers=admin_headers)).json()["data"]
    assert any(i["metric"] == "perf.cold_start" and i["n"] >= 2 for i in perf["items"])
    usage = (await client.get("/admin/v1/analytics/usage", headers=admin_headers)).json()["data"]
    assert any(i["event"] == "activity.join_succeeded" for i in usage["items"])
    errs = (await client.get("/admin/v1/analytics/errors", headers=admin_headers)).json()["data"]
    assert any(i["key"] == "/api/v1/x" for i in errs["items"])

    # RBAC / masking / audit
    analyst = await _admin_login(client, admin_headers, "analyst")
    support = await _admin_login(client, admin_headers, "support")
    operator = await _admin_login(client, admin_headers, "operator")

    r = await client.get("/admin/v1/analytics/events", params={"anon_id": anon}, headers=analyst)
    data = r.json()["data"]
    assert data["masked"] is True and data["items"], r.text
    first = data["items"][0]
    assert first["user_id"].startswith("u_") and first["anon_id"].startswith("d_") and "ip_hash" not in first
    props_blob = json.dumps([i["props"] for i in data["items"]])
    assert "13800138000" not in props_blob and '"phone":' not in props_blob

    r = await client.get("/admin/v1/analytics/events", params={"user_id": user["id"]}, headers=analyst)
    assert r.status_code == 403
    r = await client.get("/admin/v1/analytics/events", params={"user_id": user["id"]}, headers=support)
    assert r.status_code == 200 and r.json()["data"]["masked"] is False
    assert r.json()["data"]["items"][0]["user_id"] == user["id"]
    r = await client.get("/admin/v1/analytics/events", params={"anon_id": anon}, headers=operator)
    assert r.status_code == 403  # operators only see aggregates
    r = await client.get("/admin/v1/analytics/events", headers=analyst)
    assert r.status_code == 400  # needs at least one filter

    r = await client.get("/admin/v1/analytics/events/export", params={"anon_id": anon}, headers=analyst)
    assert r.status_code == 422  # reason required
    r = await client.get("/admin/v1/analytics/events/export", params={"anon_id": anon, "reason": "渠道转化分析"}, headers=analyst)
    assert r.status_code == 200 and "text/csv" in r.headers["content-type"]
    assert "13800138000" not in r.text and "u_" in r.text
    r = await client.get("/admin/v1/analytics/events/export", params={"anon_id": anon, "reason": "客服排障"}, headers=support)
    assert r.status_code == 403
    assert (await client.get("/admin/v1/analytics/overview", headers=support)).status_code == 403

    logs = (await client.get("/admin/v1/audit-logs?limit=50", headers=admin_headers)).json()["data"]["items"]
    actions = {i["action"] for i in logs}
    assert {"analytics_event_lookup", "analytics_event_export", "admin_create"} <= actions
    exp = next(i for i in logs if i["action"] == "analytics_event_export")
    assert exp["detail"]["reason"] == "渠道转化分析" and exp["detail"]["unmasked"] is False
    assert (await client.get("/admin/v1/audit-logs", headers=analyst)).status_code == 403

    # admin account safety
    me = (await client.get("/admin/v1/auth/me", headers=admin_headers)).json()["data"]
    r = await client.put(f"/admin/v1/admins/{me['id']}", json={"is_active": False}, headers=admin_headers)
    assert r.status_code == 409
    assert (await client.get("/admin/v1/admins", headers=analyst)).status_code == 403
    roles = (await client.get("/admin/v1/roles", headers=analyst)).json()["data"]["items"]
    assert {"superadmin", "operator", "auditor", "support", "finance", "analyst"} <= {x["key"] for x in roles}

    # erase my data
    r = await client.delete("/api/v1/analytics/me", params={"anon_id": anon}, headers=user["h"])
    assert r.json()["data"]["deleted"] >= 10
    r = await client.get("/admin/v1/analytics/events", params={"anon_id": anon}, headers=analyst)
    assert r.json()["data"]["items"] == []
