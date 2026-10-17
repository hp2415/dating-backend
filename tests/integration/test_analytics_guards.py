"""Ingest guards: rate limit, batch cap, anonymous erasure, retention, 18+ gate, underage onboarding."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

pytestmark = pytest.mark.asyncio


def _ev(name="page.viewed", anon="a", **kw):
    return {"event_id": str(uuid4()), "event_name": name, "anon_id": anon, "session_id": "s1",
            "occurred_at": datetime.now(timezone.utc).isoformat(), "screen": "x", **kw}


def _batch(events):
    return {"schema_version": 2, "sent_at": datetime.now(timezone.utc).isoformat(), "events": events}


async def test_rate_limit_per_device(client, monkeypatch):
    from app.shared.config import settings

    monkeypatch.setattr(settings, "analytics_ingest_per_minute", 3)
    anon = f"rl-{uuid4().hex[:8]}"
    codes = []
    for _ in range(5):
        r = await client.post("/api/v1/analytics/events", json=_batch([_ev(anon=anon)]))
        codes.append(r.status_code)
    assert codes[:3] == [200, 200, 200] and codes[3:] == [429, 429]


async def test_batch_cap_and_schema_version(client, monkeypatch):
    from app.shared.config import settings

    monkeypatch.setattr(settings, "analytics_max_batch", 5)
    anon = f"cap-{uuid4().hex[:8]}"
    r = await client.post("/api/v1/analytics/events", json=_batch([_ev(anon=anon) for _ in range(6)]))
    assert r.status_code == 413
    r = await client.post("/api/v1/analytics/events", json={**_batch([_ev(anon=anon)]), "schema_version": 99})
    assert r.status_code == 400


async def test_kill_switch_acknowledges_without_storing(client, monkeypatch):
    from app.shared.config import settings

    monkeypatch.setattr(settings, "analytics_enabled", False)
    r = await client.post("/api/v1/analytics/events", json=_batch([_ev(anon="ks")]))
    assert r.status_code == 200 and r.json()["data"]["accepted"] == 0
    cfg = (await client.get("/api/v1/analytics/config")).json()["data"]
    assert cfg["enabled"] is False


async def test_anonymous_erasure_by_device_secret(client):
    anon = f"gone-{uuid4().hex[:8]}"
    r = await client.post("/api/v1/analytics/events", json=_batch([_ev(anon=anon), _ev("page.left", anon=anon)]))
    assert r.json()["data"]["accepted"] == 2
    r = await client.delete("/api/v1/analytics/me", params={"anon_id": anon})  # no session
    assert r.json()["data"]["deleted"] == 2
    assert (await client.delete("/api/v1/analytics/me")).status_code in (400, 401, 422)


async def _ensure_month_partition(db, when):
    from sqlalchemy import text

    start = when.date().replace(day=1)
    end = (start + timedelta(days=32)).replace(day=1)
    await db.execute(text(
        f"CREATE TABLE IF NOT EXISTS analytics_events_{start:%Y%m} PARTITION OF analytics_events "
        f"FOR VALUES FROM ('{start}') TO ('{end}')"))


async def test_retention_deletes_old_rows_and_nulls_ip_hash(client):
    from sqlalchemy import text

    from app.modules.analytics.partitions import enforce_retention
    from app.shared.db import SessionLocal

    anon = f"ret-{uuid4().hex[:8]}"
    await client.post("/api/v1/analytics/events", json=_batch([_ev(anon=anon) for _ in range(3)]))
    async with SessionLocal() as db:
        await _ensure_month_partition(db, datetime.now(timezone.utc) - timedelta(days=40))
        await _ensure_month_partition(db, datetime.now(timezone.utc) - timedelta(days=400))
        # make one row 40 days old (past ip_hash window, inside retention)
        await db.execute(
            text("UPDATE analytics_events SET received_at = now() - interval '40 days' "
                 "WHERE id = (SELECT min(id) FROM analytics_events WHERE anon_id = :a)"), {"a": anon})
        res = await enforce_retention(db, keep_days=180, ip_hash_days=30)
        await db.commit()
        old_ip = (await db.execute(
            text("SELECT count(*) FROM analytics_events WHERE anon_id=:a AND ip_hash IS NOT NULL AND received_at < now() - interval '30 days'"),
            {"a": anon})).scalar()
        assert old_ip == 0 and res["ip_hash_nulled"] >= 1
        await _ensure_month_partition(db, datetime.now(timezone.utc) - timedelta(days=400))  # first run dropped the empty one
        # a row far past the retention window is removed (partition drop or boundary delete)
        await db.execute(
            text("UPDATE analytics_events SET received_at = now() - interval '400 days' "
                 "WHERE id = (SELECT min(id) FROM analytics_events WHERE anon_id = :a)"), {"a": anon})
        await enforce_retention(db, keep_days=180, ip_hash_days=30)
        await db.commit()
        left = (await db.execute(text("SELECT count(*) FROM analytics_events WHERE anon_id=:a"), {"a": anon})).scalar()
        assert left == 2


async def test_underage_birthday_rejected(client, make_user):
    user = await make_user("未成年测试")
    today = datetime.now(timezone.utc).date()
    kid = today.replace(year=today.year - 17).isoformat()
    adult = today.replace(year=today.year - 25).isoformat()
    r = await client.put("/api/v1/me/profile", json={"birthday": kid}, headers=user["h"])
    assert r.json()["code"] != 0, r.text
    r = await client.put("/api/v1/me/profile", json={"birthday": adult}, headers=user["h"])
    assert r.json()["code"] == 0, r.text
