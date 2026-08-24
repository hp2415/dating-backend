from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import case, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Activity,
    ActivityParticipant,
    ActivityStatus,
    AuditStatus,
    Block,
    Match,
    MatchStatus,
    MediaAsset,
    ParticipantStatus,
    Swipe,
    User,
    UserPreference,
    UserProfile,
    UserStatus,
)
from app.modules.activity.service import ActivityService, CATEGORIES
from app.modules.recommend.activity_scorer import ScoredActivity, ScorerContext, score_activity
from app.modules.recommend.buddy_scorer import is_online, score_buddy
from app.modules.recommend.engagement import EngagementStore, derive_tags
from app.modules.recommend.shelf_builder import build_shelves, pick_featured
from app.modules.user.service import calc_age
from app.shared.errors import AppError
from app.shared.response import ErrorCodes


class EngagementRequest(BaseModel):
    activity_id: UUID
    event: str = Field(pattern="^(view|favorite|join)$")


class RecommendService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def browse_activities(
        self,
        user: User,
        *,
        city: str | None = None,
        category: str | None = None,
        limit: int = 50,
    ) -> dict:
        stmt = (
            select(Activity)
            .where(Activity.status == ActivityStatus.PUBLISHED.value)
            .order_by(Activity.created_at.desc())
            .limit(limit)
        )
        if city:
            stmt = stmt.where(Activity.city == city)
        if category and category in CATEGORIES:
            stmt = stmt.where(Activity.category == category)

        rows = list((await self.db.execute(stmt)).scalars().all())
        activity_svc = ActivityService(self.db)
        scored: list[ScoredActivity] = []
        for idx, activity in enumerate(rows):
            brief = await activity_svc._brief(activity, viewer_id=user.id, include_members=False)
            members = await self._member_names(activity.id)
            tags = derive_tags(activity.title, activity.description or "", activity.category)
            scored.append(
                ScoredActivity(
                    id=str(activity.id),
                    title=activity.title,
                    description=activity.description or "",
                    category=activity.category,
                    tags=tags,
                    capacity=int(activity.capacity or 0),
                    join_count=int(activity.join_count or 0),
                    media=activity.media or [],
                    joined=bool(brief.get("joined")),
                    start_at=activity.start_at,
                    distance_km=None,
                    member_names=members,
                    brief=brief,
                    catalog_index=idx,
                )
            )

        profile = user.profile
        interests = list(profile.tags or []) if profile else []
        eng = EngagementStore(user.id)
        tag_w, cat_w = await eng.weights()
        friend_names = await self._friend_names(user.id)
        ctx = ScorerContext(
            user_interests=interests,
            current_user_name=(profile.display_name if profile else None) or "",
            friend_names=friend_names,
            tag_weights=tag_w,
            category_weights=cat_w,
            now=datetime.now(timezone.utc),
        )
        for a in scored:
            score_activity(a, ctx)

        featured = pick_featured(scored, ctx)
        shelves = build_shelves(scored, ctx)

        def pack(a: ScoredActivity) -> dict:
            item = dict(a.brief)
            item["score"] = round(a.score, 2)
            item["tags"] = a.tags
            item["distance_km"] = a.distance_km
            return item

        return {
            "featured": pack(featured) if featured else None,
            "shelves": [
                {
                    "id": s.id,
                    "title": s.title,
                    "subtitle": s.subtitle,
                    "layout": s.layout,
                    "items": [pack(i) for i in s.items],
                }
                for s in shelves
            ],
        }

    async def track_engagement(self, user: User, body: EngagementRequest) -> dict:
        activity = await self.db.get(Activity, body.activity_id)
        if activity is None:
            raise AppError(ErrorCodes.ACTIVITY_NOT_FOUND, "活动不存在", status_code=404)
        tags = derive_tags(activity.title, activity.description or "", activity.category)
        await EngagementStore(user.id).record(body.event, category=activity.category, tags=tags)
        return {"recorded": True, "event": body.event, "activity_id": str(body.activity_id)}

    async def record_engagement_silent(self, user_id: UUID, activity: Activity, event: str) -> None:
        tags = derive_tags(activity.title, activity.description or "", activity.category)
        await EngagementStore(user_id).record(event, category=activity.category, tags=tags)

    async def recommend_buddies(self, user: User, *, limit: int = 20) -> dict:
        if user.status == UserStatus.LIMITED.value:
            raise AppError(ErrorCodes.USER_LIMITED, "账号功能受限", status_code=403)
        if not user.profile_completed or not user.discoverable:
            return {"items": []}

        pref = user.preference or UserPreference(user_id=user.id, want_genders=[], age_min=18, age_max=50)
        interacted = select(Swipe.target_id).where(Swipe.actor_id == user.id)
        matched_peers = select(
            case((Match.user_low == user.id, Match.user_high), else_=Match.user_low)
        ).where(
            Match.status == MatchStatus.ACTIVE.value,
            or_(Match.user_low == user.id, Match.user_high == user.id),
        )
        blocked = select(Block.blocked_id).where(Block.blocker_id == user.id)
        blocked_by = select(Block.blocker_id).where(Block.blocked_id == user.id)

        stmt = (
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
            .limit(limit * 4)
        )
        if pref.want_genders:
            stmt = stmt.where(UserProfile.gender.in_(pref.want_genders))

        candidates = list((await self.db.execute(stmt)).scalars().all())
        my_tags = list((user.profile.tags if user.profile else []) or [])
        now = datetime.now(timezone.utc)
        scored_rows: list[tuple[int, dict]] = []
        for c in candidates:
            age = calc_age(c.profile.birthday if c.profile else None)
            if age is None or age < pref.age_min or age > pref.age_max:
                continue
            if c.preference and c.preference.want_genders and user.profile:
                if user.profile.gender not in c.preference.want_genders and user.profile.gender != "unknown":
                    continue
            tags = list((c.profile.tags if c.profile else []) or [])
            online = is_online(c.last_active_at, now=now)
            available = bool(c.discoverable and c.profile_completed)
            match_score, shared, reason = score_buddy(
                profile_tags=tags,
                my_interests=my_tags,
                distance_km=None,
                available=available,
                online=online,
            )
            card = await self._buddy_card(c)
            card["match_score"] = match_score
            card["shared_tags"] = shared
            card["distance_km"] = None
            card["reason"] = reason
            card["online"] = online
            card["available"] = available
            scored_rows.append((match_score, card))

        scored_rows.sort(key=lambda x: (-x[0], x[1].get("display_name") or ""))
        return {"items": [c for _, c in scored_rows[:limit]]}

    async def _buddy_card(self, user: User) -> dict:
        profile = user.profile
        avatar_url = None
        if profile and profile.avatar_media_id:
            media = await self.db.get(MediaAsset, profile.avatar_media_id)
            if media and media.audit_status != AuditStatus.REJECTED.value:
                avatar_url = media.url
        return {
            "id": user.id,
            "display_name": (profile.display_name if profile else None) or "用户",
            "age": calc_age(profile.birthday if profile else None),
            "city": profile.city if profile else None,
            "bio": profile.bio if profile else None,
            "tags": (profile.tags if profile else []) or [],
            "avatar_url": avatar_url,
            "gender": (profile.gender if profile else "unknown"),
            "completion_score": (profile.completion_score if profile else 0),
        }

    async def _member_names(self, activity_id: UUID) -> list[str]:
        result = await self.db.execute(
            select(ActivityParticipant.user_id).where(
                ActivityParticipant.activity_id == activity_id,
                ActivityParticipant.status == ParticipantStatus.JOINED.value,
            )
        )
        names: list[str] = []
        for uid in result.scalars().all():
            profile = await self.db.get(UserProfile, uid)
            names.append((profile.display_name if profile else None) or "用户")
        return names

    async def _friend_names(self, user_id: UUID) -> set[str]:
        """Approximate friends as active match peers' display names."""
        result = await self.db.execute(
            select(Match).where(
                Match.status == MatchStatus.ACTIVE.value,
                or_(Match.user_low == user_id, Match.user_high == user_id),
            )
        )
        names: set[str] = set()
        for m in result.scalars().all():
            peer_id = m.user_high if m.user_low == user_id else m.user_low
            profile = await self.db.get(UserProfile, peer_id)
            if profile and profile.display_name:
                names.add(profile.display_name)
        return names
