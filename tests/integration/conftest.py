"""Integration fixtures — need a migrated Postgres.

    DATABASE_URL=postgresql+asyncpg://... TEST_DATABASE_URL=1 alembic upgrade head
    DATABASE_URL=postgresql+asyncpg://... TEST_DATABASE_URL=1 pytest tests/integration

Skipped automatically when ``TEST_DATABASE_URL`` is unset or fakeredis is missing.
"""

import os
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set")


def pytest_collection_modifyitems(config, items):
    skip = pytest.mark.skip(reason="TEST_DATABASE_URL not set")
    if os.environ.get("TEST_DATABASE_URL"):
        return
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(skip)


@pytest.fixture
async def client():
    fakeredis = pytest.importorskip("fakeredis")
    import fakeredis.aioredis as fr
    import httpx

    import app.shared.redis_client as rc
    from app.main import app
    from app.shared.db import engine

    from app.modules.clubs.seed import ensure_official_clubs
    from app.shared.db import SessionLocal

    async with SessionLocal() as db:
        await ensure_official_clubs(db)
    rc._redis = fr.FakeRedis(decode_responses=True)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await rc.close_redis()
    await engine.dispose()


@pytest.fixture
async def make_user():
    from app.models import User, UserProfile, UserStatus
    from app.shared.db import SessionLocal
    from app.shared.security import create_access_token

    async def _make(name: str = "测试用户"):
        async with SessionLocal() as db:
            uid = uuid4()
            db.add(User(id=uid, phone=f"188{uid.int % 10**8:08d}", status=UserStatus.ACTIVE.value,
                        discoverable=True, profile_completed=True))
            await db.flush()
            db.add(UserProfile(user_id=uid, display_name=name))
            await db.commit()
        return {"id": str(uid), "h": {"Authorization": f"Bearer {create_access_token(user_id=str(uid))}"}}

    return _make


@pytest.fixture
async def admin_headers():
    from sqlalchemy import select

    from app.models import AdminUser
    from app.modules.admin.seed import ensure_default_admin
    from app.shared.db import SessionLocal
    from app.shared.security import create_admin_access_token

    async with SessionLocal() as db:
        await ensure_default_admin(db)
        admin = (await db.execute(select(AdminUser).where(AdminUser.username == "admin"))).scalar_one()
        token = create_admin_access_token(admin_id=str(admin.id), role=admin.role, username=admin.username)
    return {"Authorization": f"Bearer {token}"}
