from uuid import UUID

from sqlalchemy import Select, case, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    AuditStatus,
    Block,
    Match,
    MatchStatus,
    MediaAsset,
    Swipe,
    User,
    UserPreference,
    UserProfile,
    UserStatus,
)
from app.modules.user.service import calc_age
from app.shared.config import settings
from app.shared.errors import AppError
from app.shared.redis_client import get_redis
from app.shared.response import ErrorCodes


def _ordered_pair(a: UUID, b: UUID) -> tuple[UUID, UUID]:
    return (a, b) if str(a) < str(b) else (b, a)


class DiscoverService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.redis = get_redis()

    async def get_cards(self, user: User, cursor: str | None, limit: int | None = None) -> dict:
        limit = limit or settings.discover_page_size
        if user.status == UserStatus.LIMITED.value:
            raise AppError(ErrorCodes.USER_LIMITED, "账号功能受限，暂时无法浏览推荐", status_code=403)
        if not user.profile_completed or not user.discoverable:
            return {"items": [], "next_cursor": None, "remaining_estimate": 0}

        pref = user.preference or UserPreference(user_id=user.id, want_genders=[], age_min=18, age_max=50)
        interacted = select(Swipe.target_id).where(Swipe.actor_id == user.id)
        matched_peers = select(
            case(
                (Match.user_low == user.id, Match.user_high),
                else_=Match.user_low,
            )
        ).where(
            Match.status == MatchStatus.ACTIVE.value,
            or_(Match.user_low == user.id, Match.user_high == user.id),
        )
        blocked = select(Block.blocked_id).where(Block.blocker_id == user.id)
        blocked_by = select(Block.blocker_id).where(Block.blocked_id == user.id)

        stmt: Select = (
            select(User)
            .join(UserProfile, UserProfile.user_id == User.id)
            .where(
                User.id != user.id,
                User.status == UserStatus.ACTIVE.value,
                User.discoverable.is_(True),
                User.profile_completed.is_(True),
                not_(User.id.in_(interacted)),
                not_(User.id.in_(matched_peers)),
                not_(User.id.in_(blocked)),
                not_(User.id.in_(blocked_by)),
            )
            .options(selectinload(User.profile), selectinload(User.preference))
            .order_by(UserProfile.completion_score.desc(), User.last_active_at.desc().nullslast(), User.id.asc())
            .limit(limit * 3)
        )

        if pref.want_genders:
            stmt = stmt.where(UserProfile.gender.in_(pref.want_genders))

        if cursor:
            stmt = stmt.where(User.id > UUID(cursor))

        result = await self.db.execute(stmt)
        candidates = list(result.scalars().all())

        # Age filter in Python (birthday -> age)
        filtered: list[User] = []
        for c in candidates:
            age = calc_age(c.profile.birthday if c.profile else None)
            if age is None:
                continue
            if age < pref.age_min or age > pref.age_max:
                continue
            # Mutual preference soft filter: if candidate has want_genders, check my gender
            if c.preference and c.preference.want_genders and user.profile:
                if user.profile.gender not in c.preference.want_genders and user.profile.gender != "unknown":
                    continue
            filtered.append(c)

        # Redis exposure: demote recently shown
        exposure_key = f"discover:exposed:{user.id}"
        exposed_ids = await self.redis.smembers(exposure_key)
        fresh = [c for c in filtered if str(c.id) not in exposed_ids]
        pool = fresh or filtered
        page = pool[:limit]

        items = []
        for c in page:
            items.append(await self._to_card(c))
            await self.redis.sadd(exposure_key, str(c.id))
        if page:
            await self.redis.expire(exposure_key, settings.discover_exposure_ttl_seconds)

        next_cursor = str(page[-1].id) if len(page) == limit else None
        return {
            "items": items,
            "next_cursor": next_cursor,
            "remaining_estimate": max(len(pool) - len(page), 0),
        }

    async def _to_card(self, user: User) -> dict:
        profile = user.profile
        avatar_url = None
        if profile and profile.avatar_media_id:
            media = await self.db.get(MediaAsset, profile.avatar_media_id)
            if media and media.audit_status != AuditStatus.REJECTED.value:
                avatar_url = media.url
        age = calc_age(profile.birthday if profile else None)
        return {
            "id": user.id,
            "display_name": (profile.display_name if profile else None) or "用户",
            "age": age,
            "city": profile.city if profile else None,
            "bio": profile.bio if profile else None,
            "tags": (profile.tags if profile else []) or [],
            "avatar_url": avatar_url,
            "gender": (profile.gender if profile else "unknown"),
            "completion_score": (profile.completion_score if profile else 0),
        }
