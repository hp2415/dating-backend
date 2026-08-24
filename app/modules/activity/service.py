from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Activity,
    ActivityComment,
    ActivityLike,
    ActivityParticipant,
    ActivityStatus,
    AuditStatus,
    MediaAsset,
    ParticipantRole,
    ParticipantStatus,
    User,
    UserProfile,
    UserStatus,
)
from app.shared.errors import AppError
from app.shared.response import ErrorCodes

CATEGORIES = {"food", "sport", "travel", "game", "study", "outdoors", "other"}


class MediaItemIn(BaseModel):
    type: str = Field(pattern="^(image|video)$")
    media_id: UUID | None = None
    url: str | None = Field(default=None, max_length=1024)


class CreateActivityRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)
    category: str = Field(default="other", max_length=32)
    city: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=256)
    lat: str | None = Field(default=None, max_length=32)
    lng: str | None = Field(default=None, max_length=32)
    start_at: datetime | None = None
    end_at: datetime | None = None
    capacity: int = Field(default=10, ge=2, le=200)
    media: list[MediaItemIn] = Field(default_factory=list, max_length=9)


class CreateCommentRequest(BaseModel):
    content: str = Field(min_length=1, max_length=1000)


class ActivityService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, user: User, body: CreateActivityRequest) -> dict:
        if user.status == UserStatus.LIMITED.value:
            raise AppError(ErrorCodes.USER_LIMITED, "账号功能受限，无法发起活动", status_code=403)
        if not user.profile_completed:
            raise AppError(ErrorCodes.USER_NOT_COMPLETED, "请先完善资料")
        category = body.category if body.category in CATEGORIES else "other"
        media = await self._normalize_media(user.id, body.media)

        activity = Activity(
            id=uuid4(),
            host_id=user.id,
            title=body.title.strip(),
            description=(body.description or "").strip(),
            category=category,
            city=body.city,
            address=body.address,
            lat=body.lat,
            lng=body.lng,
            start_at=body.start_at,
            end_at=body.end_at,
            capacity=body.capacity,
            join_count=1,
            media=media,
            status=ActivityStatus.PENDING.value,
        )
        self.db.add(activity)
        await self.db.flush()
        self.db.add(
            ActivityParticipant(
                id=uuid4(),
                activity_id=activity.id,
                user_id=user.id,
                role=ParticipantRole.HOST.value,
                status=ParticipantStatus.JOINED.value,
            )
        )
        await self.db.commit()
        await self.db.refresh(activity)
        return await self._brief(activity, viewer_id=user.id, include_members=False)

    async def list_feed(
        self,
        user: User,
        *,
        city: str | None,
        category: str | None,
        mine: str | None,
        limit: int,
        offset: int,
    ) -> dict:
        stmt = select(Activity).order_by(Activity.start_at.asc().nullslast(), Activity.created_at.desc())
        if mine == "hosted":
            stmt = stmt.where(
                Activity.host_id == user.id,
                Activity.status != ActivityStatus.CANCELLED.value,
            )
        elif mine == "joined":
            joined_ids = select(ActivityParticipant.activity_id).where(
                ActivityParticipant.user_id == user.id,
                ActivityParticipant.status == ParticipantStatus.JOINED.value,
            )
            stmt = stmt.where(Activity.id.in_(joined_ids), Activity.status != ActivityStatus.CANCELLED.value)
        else:
            stmt = stmt.where(Activity.status == ActivityStatus.PUBLISHED.value)
            if city:
                stmt = stmt.where(Activity.city == city)
            if category and category in CATEGORIES:
                stmt = stmt.where(Activity.category == category)

        result = await self.db.execute(stmt.offset(offset).limit(limit))
        rows = list(result.scalars().all())
        items = [await self._brief(a, viewer_id=user.id, include_members=False) for a in rows]
        return {"items": items, "limit": limit, "offset": offset}

    async def get_detail(self, user: User, activity_id: UUID) -> dict:
        activity = await self._get_visible(activity_id, user.id)
        return await self._brief(activity, viewer_id=user.id, include_members=True)

    async def join(self, user: User, activity_id: UUID) -> dict:
        if user.status == UserStatus.LIMITED.value:
            raise AppError(ErrorCodes.USER_LIMITED, "账号功能受限，无法报名", status_code=403)
        activity = await self._get_published(activity_id)
        existing = await self.db.execute(
            select(ActivityParticipant).where(
                ActivityParticipant.activity_id == activity_id,
                ActivityParticipant.user_id == user.id,
            )
        )
        row = existing.scalar_one_or_none()
        if row and row.status == ParticipantStatus.JOINED.value:
            return {"joined": True, "join_count": activity.join_count, "already": True}
        if activity.join_count >= activity.capacity:
            raise AppError(ErrorCodes.ACTIVITY_FULL, "活动名额已满", status_code=409)

        if row:
            row.status = ParticipantStatus.JOINED.value
            row.role = ParticipantRole.MEMBER.value
        else:
            self.db.add(
                ActivityParticipant(
                    id=uuid4(),
                    activity_id=activity_id,
                    user_id=user.id,
                    role=ParticipantRole.MEMBER.value,
                    status=ParticipantStatus.JOINED.value,
                )
            )
        activity.join_count = int(activity.join_count or 0) + 1
        await self.db.commit()
        try:
            from app.modules.recommend.service import RecommendService

            await RecommendService(self.db).record_engagement_silent(user.id, activity, "join")
        except Exception:  # noqa: BLE001
            pass
        return {"joined": True, "join_count": activity.join_count, "already": False}

    async def quit(self, user: User, activity_id: UUID) -> dict:
        activity = await self.db.get(Activity, activity_id)
        if activity is None or activity.status == ActivityStatus.CANCELLED.value:
            raise AppError(ErrorCodes.ACTIVITY_NOT_FOUND, "活动不存在", status_code=404)
        if activity.host_id == user.id:
            raise AppError(ErrorCodes.ACTIVITY_FORBIDDEN, "发起人不能退出，请取消活动", status_code=403)

        result = await self.db.execute(
            select(ActivityParticipant).where(
                ActivityParticipant.activity_id == activity_id,
                ActivityParticipant.user_id == user.id,
                ActivityParticipant.status == ParticipantStatus.JOINED.value,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return {"joined": False, "join_count": activity.join_count}
        row.status = ParticipantStatus.QUIT.value
        activity.join_count = max(int(activity.join_count or 1) - 1, 1)
        await self.db.commit()
        return {"joined": False, "join_count": activity.join_count}

    async def list_members(self, user: User, activity_id: UUID) -> dict:
        await self._get_visible(activity_id, user.id)
        result = await self.db.execute(
            select(ActivityParticipant)
            .where(
                ActivityParticipant.activity_id == activity_id,
                ActivityParticipant.status == ParticipantStatus.JOINED.value,
            )
            .order_by(ActivityParticipant.joined_at.asc())
        )
        rows = list(result.scalars().all())
        items = []
        for p in rows:
            items.append(await self._member_brief(p))
        return {"items": items}

    async def like(self, user: User, activity_id: UUID) -> dict:
        activity = await self._get_published(activity_id)
        existing = await self.db.execute(
            select(ActivityLike).where(
                ActivityLike.activity_id == activity_id,
                ActivityLike.user_id == user.id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return {"liked": True, "like_count": activity.like_count}
        self.db.add(ActivityLike(id=uuid4(), activity_id=activity_id, user_id=user.id))
        activity.like_count = int(activity.like_count or 0) + 1
        await self.db.commit()
        try:
            from app.modules.recommend.service import RecommendService

            await RecommendService(self.db).record_engagement_silent(user.id, activity, "favorite")
        except Exception:  # noqa: BLE001
            pass
        return {"liked": True, "like_count": activity.like_count}

    async def unlike(self, user: User, activity_id: UUID) -> dict:
        activity = await self._get_published(activity_id)
        result = await self.db.execute(
            select(ActivityLike).where(
                ActivityLike.activity_id == activity_id,
                ActivityLike.user_id == user.id,
            )
        )
        row = result.scalar_one_or_none()
        if row is not None:
            await self.db.delete(row)
            activity.like_count = max(int(activity.like_count or 0) - 1, 0)
            await self.db.commit()
        return {"liked": False, "like_count": activity.like_count}

    async def list_comments(self, user: User, activity_id: UUID, limit: int, offset: int) -> dict:
        await self._get_visible(activity_id, user.id)
        result = await self.db.execute(
            select(ActivityComment)
            .where(
                ActivityComment.activity_id == activity_id,
                ActivityComment.status == "visible",
            )
            .order_by(ActivityComment.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
        rows = list(result.scalars().all())
        items = [await self._comment_brief(c) for c in rows]
        return {"items": items, "limit": limit, "offset": offset}

    async def add_comment(self, user: User, activity_id: UUID, body: CreateCommentRequest) -> dict:
        if user.status == UserStatus.LIMITED.value:
            raise AppError(ErrorCodes.USER_LIMITED, "账号功能受限，无法评论", status_code=403)
        activity = await self._get_published(activity_id)
        comment = ActivityComment(
            id=uuid4(),
            activity_id=activity_id,
            author_id=user.id,
            content=body.content.strip(),
            status="visible",
        )
        self.db.add(comment)
        activity.comment_count = int(activity.comment_count or 0) + 1
        await self.db.commit()
        await self.db.refresh(comment)
        return await self._comment_brief(comment)

    async def _normalize_media(self, user_id: UUID, items: list[MediaItemIn]) -> list[dict]:
        out: list[dict] = []
        for item in items:
            if item.media_id is not None:
                media = await self.db.get(MediaAsset, item.media_id)
                if media is None or media.owner_id != user_id:
                    raise AppError(ErrorCodes.MEDIA_FORBIDDEN, "媒体资源无效")
                if media.audit_status == AuditStatus.REJECTED.value:
                    raise AppError(ErrorCodes.MEDIA_FORBIDDEN, "媒体未通过审核")
                out.append(
                    {
                        "type": item.type,
                        "media_id": str(media.id),
                        "url": media.url,
                        "audit_status": media.audit_status,
                    }
                )
            elif item.url:
                out.append(
                    {
                        "type": item.type,
                        "media_id": None,
                        "url": item.url,
                        "audit_status": "placeholder",
                    }
                )
            else:
                raise AppError(ErrorCodes.ACTIVITY_INVALID, "媒体需提供 media_id 或 url")
        return out

    async def _get_published(self, activity_id: UUID) -> Activity:
        activity = await self.db.get(Activity, activity_id)
        if activity is None or activity.status != ActivityStatus.PUBLISHED.value:
            raise AppError(ErrorCodes.ACTIVITY_NOT_FOUND, "活动不存在或未发布", status_code=404)
        return activity

    async def _get_visible(self, activity_id: UUID, viewer_id: UUID) -> Activity:
        activity = await self.db.get(Activity, activity_id)
        if activity is None or activity.status == ActivityStatus.CANCELLED.value:
            raise AppError(ErrorCodes.ACTIVITY_NOT_FOUND, "活动不存在", status_code=404)
        if activity.status == ActivityStatus.PUBLISHED.value:
            return activity
        if activity.host_id == viewer_id:
            return activity
        # joined members can see pending? No - only host sees pending/rejected
        raise AppError(ErrorCodes.ACTIVITY_NOT_FOUND, "活动不存在或未发布", status_code=404)

    async def _liked(self, activity_id: UUID, user_id: UUID) -> bool:
        result = await self.db.execute(
            select(ActivityLike.id)
            .where(ActivityLike.activity_id == activity_id, ActivityLike.user_id == user_id)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _joined(self, activity_id: UUID, user_id: UUID) -> bool:
        result = await self.db.execute(
            select(ActivityParticipant.id)
            .where(
                ActivityParticipant.activity_id == activity_id,
                ActivityParticipant.user_id == user_id,
                ActivityParticipant.status == ParticipantStatus.JOINED.value,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _author_brief(self, user_id: UUID) -> dict:
        profile = await self.db.get(UserProfile, user_id)
        return {
            "id": user_id,
            "display_name": (profile.display_name if profile else None) or "用户",
            "avatar_url": None,
        }

    async def _member_brief(self, p: ActivityParticipant) -> dict:
        author = await self._author_brief(p.user_id)
        return {
            "user_id": p.user_id,
            "display_name": author["display_name"],
            "avatar_url": author["avatar_url"],
            "role": p.role,
            "joined_at": p.joined_at.isoformat() if p.joined_at else "",
        }

    async def _comment_brief(self, c: ActivityComment) -> dict:
        author = await self._author_brief(c.author_id)
        return {
            "id": c.id,
            "activity_id": c.activity_id,
            "author": author,
            "content": c.content,
            "created_at": c.created_at.isoformat() if c.created_at else "",
        }

    async def _brief(self, activity: Activity, viewer_id: UUID, include_members: bool) -> dict:
        host = await self._author_brief(activity.host_id)
        liked = await self._liked(activity.id, viewer_id)
        joined = await self._joined(activity.id, viewer_id)
        data = {
            "id": activity.id,
            "host": host,
            "title": activity.title,
            "description": activity.description,
            "category": activity.category,
            "city": activity.city,
            "address": activity.address,
            "lat": activity.lat,
            "lng": activity.lng,
            "start_at": activity.start_at.isoformat() if activity.start_at else None,
            "end_at": activity.end_at.isoformat() if activity.end_at else None,
            "capacity": activity.capacity,
            "join_count": activity.join_count,
            "media": activity.media or [],
            "status": activity.status,
            "like_count": activity.like_count,
            "comment_count": activity.comment_count,
            "liked": liked,
            "joined": joined,
            "is_host": activity.host_id == viewer_id,
            "created_at": activity.created_at.isoformat() if activity.created_at else "",
        }
        if include_members:
            result = await self.db.execute(
                select(ActivityParticipant)
                .where(
                    ActivityParticipant.activity_id == activity.id,
                    ActivityParticipant.status == ParticipantStatus.JOINED.value,
                )
                .order_by(ActivityParticipant.joined_at.asc())
            )
            data["members"] = [await self._member_brief(p) for p in result.scalars().all()]
        return data
