"""Seed discoverable demo users for M2 card browsing."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AuditStatus,
    MediaAsset,
    MediaType,
    User,
    UserPreference,
    UserProfile,
    UserStatus,
)
from app.shared.config import settings

DEMO_NAMES = [
    ("林夏", "female", "上海", "喜欢城市漫步和胶片相机", ["摄影", "咖啡", "徒步"]),
    ("周然", "male", "杭州", "产品经理，偶尔写随笔", ["阅读", "健身", "美食"]),
    ("苏晚", "female", "成都", "寻找一起去 livehouse 的搭子", ["音乐", "火锅", "猫咪"]),
    ("陈屿", "male", "深圳", "工程师，周末滑板", ["滑板", "科技", "旅行"]),
    ("何安", "female", "北京", "策展助理，热爱纪录片", ["艺术", "纪录片", "展览"]),
    ("顾澄", "male", "南京", "餐饮顾问，爱试新店", ["烹饪", "美酒", "骑行"]),
    ("叶宁", "female", "广州", "设计师，喜欢海边日落", ["设计", "海边", "咖啡"]),
    ("陆泽", "male", "武汉", "健身教练，认真生活", ["健身", "篮球", "电影"]),
]

PHOTOS = [
    "https://images.unsplash.com/photo-1529626455594-4ff0802cfb7e?w=800",
    "https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?w=800",
    "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=800",
    "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=800",
    "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=800",
    "https://images.unsplash.com/photo-1531746020798-e6953c6e8e04?w=800",
    "https://images.unsplash.com/photo-1524504388940-b1c1722653e1?w=800",
    "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=800",
]


async def ensure_demo_users(db: AsyncSession) -> None:
    if not settings.seed_demo_users:
        return
    # Count discoverable seeded phones
    count = await db.scalar(
        select(func.count()).select_from(User).where(User.phone.like("1990000%"))
    )
    target = settings.seed_demo_user_count
    existing = int(count or 0)
    if existing >= target:
        return
    to_create = target - existing

    today = date.today()
    for i in range(existing, existing + to_create):
        template = DEMO_NAMES[i % len(DEMO_NAMES)]
        name, gender, city, bio, tags = template
        phone = f"1990000{i:04d}"
        user_id = uuid4()
        birthday = date(today.year - (22 + (i % 12)), ((i % 12) + 1), 10 + (i % 15))
        user = User(
            id=user_id,
            phone=phone,
            status=UserStatus.ACTIVE.value,
            discoverable=True,
            profile_completed=True,
            last_active_at=datetime.now(timezone.utc) - timedelta(hours=i % 48),
        )
        db.add(user)
        await db.flush()

        media_id = uuid4()
        photo = PHOTOS[i % len(PHOTOS)]
        db.add(
            MediaAsset(
                id=media_id,
                owner_id=user_id,
                media_type=MediaType.AVATAR.value,
                object_key=f"demo/{user_id}.jpg",
                url=photo,
                audit_status=AuditStatus.APPROVED.value,
                meta={"demo": True},
            )
        )
        db.add(
            UserProfile(
                user_id=user_id,
                display_name=f"{name}{i % 10 if i >= len(DEMO_NAMES) else ''}",
                birthday=birthday,
                gender=gender,
                city=city,
                bio=bio,
                tags=tags,
                avatar_media_id=media_id,
                completion_score=90,
            )
        )
        # Prefer opposite gender broadly for demo matching
        want = ["male"] if gender == "female" else ["female"]
        db.add(
            UserPreference(
                user_id=user_id,
                want_genders=want,
                age_min=18,
                age_max=45,
                max_distance_km=50,
            )
        )

    await db.commit()
