from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Match, MatchStatus, Swipe, SwipeAction, User, UserStatus
from app.modules.chat_gate.provider import get_im_provider
from app.modules.discover.service import DiscoverService, _ordered_pair
from app.shared.config import settings
from app.shared.errors import AppError
from app.shared.redis_client import get_redis
from app.shared.response import ErrorCodes


class MatchService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.redis = get_redis()
        self.discover = DiscoverService(db)

    async def swipe(self, user: User, target_user_id: UUID, action: str, idempotency_key: str | None) -> dict:
        if user.id == target_user_id:
            raise AppError(ErrorCodes.MATCH_INVALID, "不能对自己操作")
        if user.status == UserStatus.LIMITED.value:
            raise AppError(ErrorCodes.USER_LIMITED, "账号功能受限，暂时无法滑动", status_code=403)
        if not user.profile_completed:
            raise AppError(ErrorCodes.USER_NOT_COMPLETED, "请先完善资料")

        target = await self.db.get(User, target_user_id)
        if target is None or target.status != UserStatus.ACTIVE.value or not target.discoverable:
            raise AppError(ErrorCodes.USER_NOT_FOUND, "对方不可用", status_code=404)

        if idempotency_key:
            existed = await self.db.execute(
                select(Swipe).where(Swipe.actor_id == user.id, Swipe.idempotency_key == idempotency_key)
            )
            row = existed.scalar_one_or_none()
            if row is not None:
                match = await self._find_active_match(user.id, target_user_id)
                return {
                    "recorded": True,
                    "matched": match is not None,
                    "match": await self._match_brief(user.id, match) if match else None,
                }

        existing = await self.db.execute(
            select(Swipe).where(Swipe.actor_id == user.id, Swipe.target_id == target_user_id)
        )
        if existing.scalar_one_or_none() is not None:
            raise AppError(ErrorCodes.SWIPE_DUPLICATE, "已对该用户滑动过", status_code=409)

        if action == SwipeAction.LIKE.value:
            await self._assert_like_allowed(user)

        swipe = Swipe(
            id=uuid4(),
            actor_id=user.id,
            target_id=target_user_id,
            action=action,
            idempotency_key=idempotency_key,
        )
        self.db.add(swipe)

        matched = False
        match_brief = None
        if action == SwipeAction.LIKE.value:
            mutual = await self.db.execute(
                select(Swipe).where(
                    Swipe.actor_id == target_user_id,
                    Swipe.target_id == user.id,
                    Swipe.action == SwipeAction.LIKE.value,
                )
            )
            if mutual.scalar_one_or_none() is not None:
                match = await self._create_match(user.id, target_user_id)
                matched = True
                match_brief = await self._match_brief(user.id, match)
            await self._bump_like_count(user)

        await self.db.commit()
        return {"recorded": True, "matched": matched, "match": match_brief}

    async def list_matches(self, user: User) -> list[dict]:
        result = await self.db.execute(
            select(Match)
            .where(
                Match.status == MatchStatus.ACTIVE.value,
                or_(Match.user_low == user.id, Match.user_high == user.id),
            )
            .order_by(Match.matched_at.desc())
        )
        matches = list(result.scalars().all())
        out = []
        for m in matches:
            brief = await self._match_brief(user.id, m)
            if brief:
                out.append(brief)
        return out

    async def unmatch(self, user: User, match_id: UUID) -> dict:
        result = await self.db.execute(select(Match).where(Match.id == match_id))
        match = result.scalar_one_or_none()
        if match is None or user.id not in (match.user_low, match.user_high):
            raise AppError(ErrorCodes.MATCH_NOT_FOUND, "匹配不存在", status_code=404)
        match.status = MatchStatus.UNMATCHED.value
        match.unmatched_at = datetime.now(timezone.utc)
        await self.db.commit()
        return {"unmatched": True}

    def _like_limit_for(self, user: User) -> int:
        created = user.created_at or datetime.now(timezone.utc)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        is_new = datetime.now(timezone.utc) - created < timedelta(days=3)
        return settings.new_user_like_limit if is_new else settings.daily_like_limit

    async def _assert_like_allowed(self, user: User) -> None:
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        key = f"swipe:like:{user.id}:{day}"
        count = int(await self.redis.get(key) or 0)
        limit = self._like_limit_for(user)
        if count >= limit:
            raise AppError(ErrorCodes.MATCH_LIMIT, f"今日喜欢次数已达上限（{limit}）", status_code=429)

    async def _bump_like_count(self, user: User) -> None:
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        key = f"swipe:like:{user.id}:{day}"
        await self.redis.incr(key)
        await self.redis.expire(key, 86400)

    async def _create_match(self, a: UUID, b: UUID) -> Match:
        low, high = _ordered_pair(a, b)
        existing = await self.db.execute(
            select(Match).where(Match.user_low == low, Match.user_high == high)
        )
        match = existing.scalar_one_or_none()
        if match and match.status == MatchStatus.ACTIVE.value:
            return match
        if match:
            match.status = MatchStatus.ACTIVE.value
            match.matched_at = datetime.now(timezone.utc)
            match.unmatched_at = None
        else:
            match = Match(id=uuid4(), user_low=low, user_high=high, status=MatchStatus.ACTIVE.value)
            self.db.add(match)
            await self.db.flush()

        # Reserve IM conversation id for later SDK wiring
        provider = get_im_provider()
        conv_id = await provider.open_conversation(a, b)
        if conv_id:
            match.im_conversation_id = conv_id
        else:
            match.im_conversation_id = f"pending_{match.id}"
        return match

    async def _find_active_match(self, a: UUID, b: UUID) -> Match | None:
        low, high = _ordered_pair(a, b)
        result = await self.db.execute(
            select(Match).where(
                Match.user_low == low,
                Match.user_high == high,
                Match.status == MatchStatus.ACTIVE.value,
            )
        )
        return result.scalar_one_or_none()

    async def _match_brief(self, viewer_id: UUID, match: Match | None) -> dict | None:
        if match is None:
            return None
        peer_id = match.user_high if match.user_low == viewer_id else match.user_low
        result = await self.db.execute(
            select(User)
            .where(User.id == peer_id)
            .options(selectinload(User.profile), selectinload(User.preference))
        )
        peer = result.scalar_one_or_none()
        if peer is None:
            return None
        card = await self.discover._to_card(peer)
        return {
            "id": match.id,
            "peer": card,
            "matched_at": match.matched_at.isoformat() if match.matched_at else "",
            "status": match.status,
            "im_conversation_id": match.im_conversation_id,
        }
