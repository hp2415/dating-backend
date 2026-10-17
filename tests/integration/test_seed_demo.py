"""scripts/seed_demo_data.py end-to-end: seed → API returns it → images resolve → idempotent → reset removes only seeds."""

import argparse
import importlib.util
from pathlib import Path
from urllib.parse import urlparse

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "seed_demo_data.py"


def _load():
    spec = importlib.util.spec_from_file_location("seed_demo_data", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _args(**kw):
    base = dict(users=12, seed="7", reset=False, reseed=True, no_images=False, force=False, public_base="http://test",
                media_root="", password="Seed@123456", analytics_days=3, font="")
    base.update(kw)
    return argparse.Namespace(**base)


async def _count_users():
    from sqlalchemy import func, select

    from app.models import User
    from app.shared.db import SessionLocal

    async with SessionLocal() as db:
        return int((await db.execute(select(func.count()).select_from(User).where(User.phone.like("186000000%")))).scalar_one())


async def test_seed_demo_data(client):
    mod = _load()
    assert await mod.amain(_args()) == 0
    try:
        assert await _count_users() == 12

        # idempotent: second run adds nothing user-visible
        assert await mod.amain(_args(reseed=False)) == 0
        assert await _count_users() == 12

        # login with the documented credentials
        r = await client.post("/api/v1/auth/password/login", json={"phone": "18600000001", "password": "Seed@123456",
                                                                    "device_id": "seed-test", "platform": "android"})
        assert r.status_code == 200, r.text
        h = {"Authorization": f"Bearer {r.json()['data']['tokens']['access_token']}"}

        async def get(path, **kw):
            resp = await client.get(path, headers=h, **kw)
            assert resp.status_code == 200, (path, resp.text[:300])
            return resp.json()["data"]

        def items(d):
            return d["items"] if isinstance(d, dict) and "items" in d else d

        me = await get("/api/v1/me")
        assert me["profile"]["display_name"] == "林夏"
        wallet = await get("/api/v1/me/wallet")
        assert wallet["balance_cents"] >= 0
        assert items(await get("/api/v1/me/wallet/ledger"))
        assert items(await get("/api/v1/orders"))
        assert items(await get("/api/v1/me/refunds")) is not None
        assert items(await get("/api/v1/friends"))
        assert items(await get("/api/v1/conversations"))
        assert items(await get("/api/v1/notifications"))
        assert items(await get("/api/v1/me/bookings")) is not None
        assert items(await get("/api/v1/me/credentials"))
        assert items(await get("/api/v1/clubs"))
        assert items(await get("/api/v1/guilds"))
        assert items(await get("/api/v1/companions"))
        assert items(await get("/api/v1/announcements"))

        acts = items(await get("/api/v1/activities", params={"limit": 50}))
        assert len(acts) >= 15
        posts = items(await get("/api/v1/community/posts", params={"limit": 50}))
        assert posts

        # every image URL resolves through the /media static mount
        urls = []
        for a in acts:
            urls += [m["url"] for m in a.get("media") or []]
        for p in posts:
            urls += [m["url"] for m in p.get("media") or []]
        avatar = me["profile"].get("avatar_url") or me.get("avatar_url")
        if avatar:
            urls.append(avatar)
        assert urls, "no image URLs found in activity/post payloads"
        for url in urls[:25]:
            resp = await client.get(urlparse(url).path)
            assert resp.status_code == 200, url
            assert resp.headers["content-type"].startswith("image/"), url
            assert len(resp.content) > 500

        detail = await get(f"/api/v1/activities/{acts[0]['id']}")
        assert detail["title"]

        # ops side
        from sqlalchemy import select

        from app.models import AdminUser
        from app.modules.admin.seed import ensure_default_admin
        from app.shared.db import SessionLocal
        from app.shared.security import create_admin_access_token

        async with SessionLocal() as db:
            await ensure_default_admin(db)
            admin = (await db.execute(select(AdminUser).where(AdminUser.username == "admin"))).scalar_one()
            ah = {"Authorization": "Bearer " + create_admin_access_token(admin_id=str(admin.id), role=admin.role, username=admin.username)}
        for path in ("/admin/v1/reports?status=pending", "/admin/v1/refunds", "/admin/v1/orders", "/admin/v1/verifications",
                     "/admin/v1/announcements", "/admin/v1/community/posts", "/admin/v1/activities", "/admin/v1/metrics/overview"):
            resp = await client.get(path, headers=ah)
            assert resp.status_code == 200, (path, resp.text[:300])
        reports = (await client.get("/admin/v1/reports?status=pending", headers=ah)).json()["data"]
        assert (reports["total"] if isinstance(reports, dict) else len(reports)) >= 5
        ov = (await client.get("/admin/v1/metrics/overview", headers=ah)).json()["data"]
        assert ov, "dashboard overview empty"
    finally:
        out = await mod.reset_seed_default()
    assert await _count_users() == 0
    assert out["users"] == 12
