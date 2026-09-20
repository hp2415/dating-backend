"""Seed default membership plans."""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MembershipPlan


DEFAULT_PLANS = [
    {
        "code": "monthly",
        "title": "月度会员",
        "price_cents": 2800,
        "duration_days": 30,
        "benefits": ["发现加权", "看谁喜欢我", "专属徽章"],
        "sort_order": 1,
    },
    {
        "code": "quarterly",
        "title": "季度会员",
        "price_cents": 6800,
        "duration_days": 90,
        "benefits": ["发现加权", "看谁喜欢我", "专属徽章", "优先客服"],
        "sort_order": 2,
    },
]


async def ensure_membership_plans(session: AsyncSession) -> None:
    for item in DEFAULT_PLANS:
        result = await session.execute(select(MembershipPlan).where(MembershipPlan.code == item["code"]))
        if result.scalar_one_or_none() is not None:
            continue
        session.add(
            MembershipPlan(
                id=uuid4(),
                code=item["code"],
                title=item["title"],
                price_cents=item["price_cents"],
                duration_days=item["duration_days"],
                benefits=item["benefits"],
                active=True,
                sort_order=item["sort_order"],
            )
        )
    await session.commit()
