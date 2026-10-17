from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Activity,
    ActivityComment,
    ActivityJourney,
    ActivityDetail,
    ActivityFavorite,
    ActivityLike,
    ActivityParticipant,
    ActivityStatus,
    AuditStatus,
    Conversation,
    ConversationKind,
    ConversationMember,
    MemberStatus,
    FeeType,
    MediaAsset,
    ParticipantRole,
    ParticipantStatus,
    User,
    UserProfile,
    UserStatus,
)
from app.modules.media.storage import expose_media, normalize_stored_media_url
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
    fee_type: str = Field(default=FeeType.FREE.value, max_length=16)
    fee_cents: int = Field(default=0, ge=0, le=10_000_000)
    fee_note: str | None = Field(default=None, max_length=120)


class UpdateActivityRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    category: str | None = Field(default=None, max_length=32)
    city: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=256)
    lat: str | None = Field(default=None, max_length=32)
    lng: str | None = Field(default=None, max_length=32)
    start_at: datetime | None = None
    end_at: datetime | None = None
    capacity: int | None = Field(default=None, ge=2, le=200)
    media: list[MediaItemIn] | None = Field(default=None, max_length=9)
    fee_type: str | None = Field(default=None, max_length=16)
    fee_cents: int | None = Field(default=None, ge=0, le=10_000_000)
    fee_note: str | None = Field(default=None, max_length=120)


class CancelActivityRequest(BaseModel):
    reason: str = Field(default="", max_length=500)


class ActivityDetailsRequest(BaseModel):
    timeline: list | None = None
    gear: list | None = None
    fee_included: list | None = None
    fee_excluded: list | None = None
    refund_notes: list | None = None
    prep_notes: list | None = None
    registration_notes: list | None = None
    host_note: str | None = Field(default=None, max_length=4000)
    gallery: list | None = None


class JoinActivityRequest(BaseModel):
    """报名可选「给发起人留言」；非空时同时向发起人发一条好友申请（source=activity）。"""

    note: str | None = Field(default=None, max_length=200)


class JourneyUpdateRequest(BaseModel):
    steps: dict | None = None
    feedback: dict | None = None


_JOURNEY_STEP_KEYS = {"marked_arrived": bool, "arrived_at": int, "opened_activity_group": bool}
_JOURNEY_FEEDBACK_KEYS = {
    "feedback_submitted": bool,
    "feedback_skipped": bool,
    "feedback_highlight": str,
    "recap_published": bool,
    "recap_skipped": bool,
}


def _pick(data: dict | None, spec: dict) -> dict:
    out: dict = {}
    for key, typ in spec.items():
        if data and key in data and data[key] is not None:
            val = data[key]
            if typ is bool:
                out[key] = bool(val)
            elif typ is int:
                try:
                    out[key] = int(val)
                except (TypeError, ValueError):
                    continue
            else:
                out[key] = str(val)[:200]
    return out


class CreateCommentRequest(BaseModel):
    content: str = Field(min_length=1, max_length=1000)


FEE_TYPES = {e.value for e in FeeType}


def _normalize_fee(fee_type: str | None, fee_cents: int | None, fee_note: str | None) -> tuple[str, int, str | None]:
    ft = (fee_type or FeeType.FREE.value).strip()
    if ft not in FEE_TYPES:
        ft = FeeType.FREE.value
    cents = int(fee_cents or 0)
    if ft == FeeType.FREE.value:
        cents = 0
    return ft, cents, (fee_note.strip() if fee_note else None)


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
        fee_type, fee_cents, fee_note = _normalize_fee(body.fee_type, body.fee_cents, body.fee_note)

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
            fee_type=fee_type,
            fee_cents=fee_cents,
            fee_note=fee_note,
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
        from app.modules.messaging.service import MessagingService

        await MessagingService(self.db).ensure_activity_group(activity, user.id)
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

    async def _lock_activity(self, activity_id: UUID) -> Activity:
        result = await self.db.execute(select(Activity).where(Activity.id == activity_id).with_for_update())
        activity = result.scalar_one_or_none()
        if activity is None or activity.status != ActivityStatus.PUBLISHED.value:
            raise AppError(ErrorCodes.ACTIVITY_NOT_FOUND, "活动不存在或未发布", status_code=404)
        return activity

    async def _participant(self, activity_id: UUID, user_id: UUID) -> ActivityParticipant | None:
        return (
            await self.db.execute(
                select(ActivityParticipant).where(
                    ActivityParticipant.activity_id == activity_id,
                    ActivityParticipant.user_id == user_id,
                )
            )
        ).scalar_one_or_none()

    async def _waitlist_position(self, activity_id: UUID, row: ActivityParticipant) -> int:
        ahead = await self.db.scalar(
            select(func.count())
            .select_from(ActivityParticipant)
            .where(
                ActivityParticipant.activity_id == activity_id,
                ActivityParticipant.status == ParticipantStatus.WAITLISTED.value,
                ActivityParticipant.waitlisted_at <= (row.waitlisted_at or datetime.now(timezone.utc)),
            )
        )
        return max(1, int(ahead or 1))

    async def join(self, user: User, activity_id: UUID, body: JoinActivityRequest | None = None) -> dict:
        if user.status == UserStatus.LIMITED.value:
            raise AppError(ErrorCodes.USER_LIMITED, "账号功能受限，无法报名", status_code=403)
        note = ((body.note if body else None) or "").strip()
        if note:
            from app.modules.safety.content_safety import guard_text

            await guard_text(self.db, note, scene="activity_join_note")
        activity = await self._lock_activity(activity_id)  # row lock: capacity check is race-free
        row = await self._participant(activity_id, user.id)
        if row and row.status == ParticipantStatus.JOINED.value:
            return {"joined": True, "join_count": activity.join_count, "already": True}
        if activity.host_id == user.id:
            raise AppError(ErrorCodes.ACTIVITY_FORBIDDEN, "发起人已在活动中", status_code=403)
        if activity.join_count >= activity.capacity:
            raise AppError(ErrorCodes.ACTIVITY_FULL, "活动名额已满，可加入候补", status_code=409)

        if row:
            row.status = ParticipantStatus.JOINED.value
            row.role = ParticipantRole.MEMBER.value
            row.waitlisted_at = None
        else:
            row = ActivityParticipant(
                id=uuid4(),
                activity_id=activity_id,
                user_id=user.id,
                role=ParticipantRole.MEMBER.value,
                status=ParticipantStatus.JOINED.value,
            )
            self.db.add(row)
        row.note = note or None
        activity.join_count = int(activity.join_count or 0) + 1
        from app.modules.events.service import DomainEventName, DomainEventService
        from app.modules.messaging.service import MessagingService

        messaging = MessagingService(self.db)
        await messaging.ensure_activity_group(activity, user.id)
        await DomainEventService(self.db).enqueue(
            name=DomainEventName.ACTIVITY_JOINED,
            aggregate_kind="activity",
            aggregate_id=activity.id,
            payload={"user_id": str(user.id), "host_id": str(activity.host_id), "has_note": bool(note)},
        )
        friend_request_sent = False
        if note:
            friend_request_sent = await self._note_to_friend_request(messaging, user, activity, note)
        await self.db.commit()
        try:
            from app.modules.recommend.service import RecommendService

            await RecommendService(self.db).record_engagement_silent(user.id, activity, "join")
        except Exception:  # noqa: BLE001
            pass
        return {
            "joined": True,
            "join_count": activity.join_count,
            "already": False,
            "friend_request_sent": friend_request_sent,
        }

    async def _note_to_friend_request(self, messaging, user: User, activity: Activity, note: str) -> bool:
        """报名留言 → 好友申请。已是好友 / 已拉黑 / 已有待处理申请时静默跳过，不影响报名。"""
        try:
            async with self.db.begin_nested():
                await messaging.send_friend_request(
                    user,
                    to_user_id=activity.host_id,
                    to_uid=None,
                    to_phone=None,
                    message=note,
                    source="activity",
                )
            return True
        except AppError:
            return False

    async def _promote_waitlist(self, activity: Activity) -> list[UUID]:
        """Fill free seats from the waitlist (FIFO). Caller holds the activity row lock."""
        promoted: list[UUID] = []
        from app.modules.events.service import DomainEventName, DomainEventService
        from app.modules.messaging.service import MessagingService

        while activity.join_count < activity.capacity:
            nxt = (
                await self.db.execute(
                    select(ActivityParticipant)
                    .where(
                        ActivityParticipant.activity_id == activity.id,
                        ActivityParticipant.status == ParticipantStatus.WAITLISTED.value,
                    )
                    .order_by(ActivityParticipant.waitlisted_at.asc().nullslast())
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
            ).scalar_one_or_none()
            if nxt is None:
                break
            nxt.status = ParticipantStatus.JOINED.value
            nxt.waitlisted_at = None
            activity.join_count = int(activity.join_count or 0) + 1
            await MessagingService(self.db).ensure_activity_group(activity, nxt.user_id)
            await DomainEventService(self.db).enqueue(
                name=DomainEventName.ACTIVITY_WAITLIST_PROMOTED,
                aggregate_kind="activity",
                aggregate_id=activity.id,
                payload={"user_id": str(nxt.user_id)},
            )
            promoted.append(nxt.user_id)
        return promoted

    async def quit(self, user: User, activity_id: UUID) -> dict:
        activity = await self.db.get(Activity, activity_id)
        if activity is None or activity.status == ActivityStatus.CANCELLED.value:
            raise AppError(ErrorCodes.ACTIVITY_NOT_FOUND, "活动不存在", status_code=404)
        if activity.host_id == user.id:
            raise AppError(ErrorCodes.ACTIVITY_FORBIDDEN, "发起人不能退出，请取消活动", status_code=403)
        activity = (
            await self.db.execute(select(Activity).where(Activity.id == activity_id).with_for_update())
        ).scalar_one()

        row = await self._participant(activity_id, user.id)
        if row is None or row.status not in {ParticipantStatus.JOINED.value, ParticipantStatus.WAITLISTED.value}:
            return {"joined": False, "join_count": activity.join_count}
        was_joined = row.status == ParticipantStatus.JOINED.value
        row.status = ParticipantStatus.QUIT.value
        row.waitlisted_at = None
        if was_joined:
            activity.join_count = max(int(activity.join_count or 1) - 1, 1)
            await self._leave_activity_group(activity, user.id)
            await self._promote_waitlist(activity)
        await self.db.commit()
        return {"joined": False, "join_count": activity.join_count}

    async def _leave_activity_group(self, activity: Activity, user_id: UUID) -> None:
        conv_id = await self.db.scalar(
            select(Conversation.id).where(
                Conversation.related_activity_id == activity.id,
                Conversation.kind == ConversationKind.ACTIVITY.value,
            )
        )
        if conv_id is None:
            return
        member = (
            await self.db.execute(
                select(ConversationMember).where(
                    ConversationMember.conversation_id == conv_id,
                    ConversationMember.user_id == user_id,
                    ConversationMember.status == MemberStatus.ACTIVE.value,
                )
            )
        ).scalar_one_or_none()
        if member is not None:
            member.status = MemberStatus.LEFT.value

    async def join_waitlist(self, user: User, activity_id: UUID) -> dict:
        if user.status == UserStatus.LIMITED.value:
            raise AppError(ErrorCodes.USER_LIMITED, "账号功能受限，无法报名", status_code=403)
        activity = await self._lock_activity(activity_id)
        if activity.host_id == user.id:
            raise AppError(ErrorCodes.ACTIVITY_FORBIDDEN, "发起人已在活动中", status_code=403)
        row = await self._participant(activity_id, user.id)
        if row and row.status == ParticipantStatus.JOINED.value:
            raise AppError(ErrorCodes.ACTIVITY_ALREADY_JOINED, "你已报名该活动", status_code=409)
        if activity.join_count < activity.capacity:
            raise AppError(ErrorCodes.ACTIVITY_INVALID, "还有名额，请直接报名", status_code=409)
        if row is None:
            row = ActivityParticipant(
                id=uuid4(), activity_id=activity_id, user_id=user.id, role=ParticipantRole.MEMBER.value
            )
            self.db.add(row)
        if row.status != ParticipantStatus.WAITLISTED.value or row.waitlisted_at is None:
            row.waitlisted_at = datetime.now(timezone.utc)
        row.status = ParticipantStatus.WAITLISTED.value
        await self.db.flush()
        position = await self._waitlist_position(activity_id, row)
        await self.db.commit()
        return {"waitlisted": True, "position": position, "join_count": activity.join_count}

    async def leave_waitlist(self, user: User, activity_id: UUID) -> dict:
        row = await self._participant(activity_id, user.id)
        if row is not None and row.status == ParticipantStatus.WAITLISTED.value:
            row.status = ParticipantStatus.QUIT.value
            row.waitlisted_at = None
            await self.db.commit()
        return {"waitlisted": False}

    async def my_status(self, user: User, activity_id: UUID) -> dict:
        activity = await self.db.get(Activity, activity_id)
        if activity is None:
            raise AppError(ErrorCodes.ACTIVITY_NOT_FOUND, "活动不存在", status_code=404)
        if activity.host_id == user.id:
            return {"status": "host", "waitlist_position": None, "note": None}
        row = await self._participant(activity_id, user.id)
        if row is None:
            return {"status": "none", "waitlist_position": None, "note": None}
        position = None
        if row.status == ParticipantStatus.WAITLISTED.value:
            position = await self._waitlist_position(activity_id, row)
        return {"status": row.status, "waitlist_position": position, "note": row.note}

    async def my_activities(self, user: User, *, status: str) -> dict:
        """我的报名：joined | waitlisted（候补）。"""
        want = ParticipantStatus.WAITLISTED.value if status == "waitlisted" else ParticipantStatus.JOINED.value
        rows = (
            await self.db.execute(
                select(Activity)
                .join(ActivityParticipant, ActivityParticipant.activity_id == Activity.id)
                .where(ActivityParticipant.user_id == user.id, ActivityParticipant.status == want)
                .order_by(Activity.start_at.asc().nullslast())
                .limit(100)
            )
        ).scalars().all()
        return {"items": [await self._brief(a, viewer_id=user.id, include_members=False) for a in rows]}

    async def get_journey(self, user: User, activity_id: UUID) -> dict:
        await self._require_participant(user, activity_id)
        row = (
            await self.db.execute(
                select(ActivityJourney).where(ActivityJourney.activity_id == activity_id, ActivityJourney.user_id == user.id)
            )
        ).scalar_one_or_none()
        return self._journey_brief(activity_id, row)

    async def put_journey(self, user: User, activity_id: UUID, body: JourneyUpdateRequest) -> dict:
        await self._require_participant(user, activity_id)
        row = (
            await self.db.execute(
                select(ActivityJourney).where(ActivityJourney.activity_id == activity_id, ActivityJourney.user_id == user.id)
            )
        ).scalar_one_or_none()
        if row is None:
            row = ActivityJourney(id=uuid4(), activity_id=activity_id, user_id=user.id, steps={}, feedback={})
            self.db.add(row)
        row.steps = {**(row.steps or {}), **_pick(body.steps, _JOURNEY_STEP_KEYS)}
        row.feedback = {**(row.feedback or {}), **_pick(body.feedback, _JOURNEY_FEEDBACK_KEYS)}
        await self.db.commit()
        return self._journey_brief(activity_id, row)

    def _journey_brief(self, activity_id: UUID, row: ActivityJourney | None) -> dict:
        return {
            "activity_id": str(activity_id),
            "steps": dict(row.steps) if row else {},
            "feedback": dict(row.feedback) if row else {},
            "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
        }

    async def _require_participant(self, user: User, activity_id: UUID) -> None:
        activity = await self.db.get(Activity, activity_id)
        if activity is None:
            raise AppError(ErrorCodes.ACTIVITY_NOT_FOUND, "活动不存在", status_code=404)
        if activity.host_id == user.id:
            return
        row = await self._participant(activity_id, user.id)
        if row is None or row.status != ParticipantStatus.JOINED.value:
            raise AppError(ErrorCodes.ACTIVITY_FORBIDDEN, "仅参与者可查看行程", status_code=403)

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
        from app.modules.safety.content_safety import guard_text

        await guard_text(self.db, body.content, scene="activity_comment")
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

    async def delete_comment(self, user: User, activity_id: UUID, comment_id: UUID) -> dict:
        comment = await self.db.get(ActivityComment, comment_id)
        if comment is None or comment.activity_id != activity_id or comment.status != "visible":
            raise AppError(ErrorCodes.ACTIVITY_NOT_FOUND, "评论不存在", status_code=404)
        activity = await self.db.get(Activity, activity_id)
        if comment.author_id != user.id and (activity is None or activity.host_id != user.id):
            raise AppError(ErrorCodes.ACTIVITY_FORBIDDEN, "无权删除该评论", status_code=403)
        comment.status = "deleted"
        if activity is not None:
            activity.comment_count = max(0, int(activity.comment_count or 1) - 1)
        await self.db.commit()
        return {"deleted": True}

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
                        "url": normalize_stored_media_url(media.url),
                        "audit_status": media.audit_status,
                    }
                )
            elif item.url:
                out.append(
                    {
                        "type": item.type,
                        "media_id": None,
                        "url": normalize_stored_media_url(item.url),
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

    async def _favorited(self, activity_id: UUID, user_id: UUID) -> bool:
        result = await self.db.execute(
            select(ActivityFavorite.id)
            .where(ActivityFavorite.activity_id == activity_id, ActivityFavorite.user_id == user_id)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def update(self, user: User, activity_id: UUID, body: UpdateActivityRequest) -> dict:
        activity = await self.db.get(Activity, activity_id)
        if activity is None or activity.status == ActivityStatus.CANCELLED.value:
            raise AppError(ErrorCodes.ACTIVITY_NOT_FOUND, "活动不存在", status_code=404)
        if activity.host_id != user.id:
            raise AppError(ErrorCodes.ACTIVITY_FORBIDDEN, "仅主办可编辑", status_code=403)
        payload = body.model_dump(exclude_unset=True)
        if "category" in payload and payload["category"] is not None:
            payload["category"] = payload["category"] if payload["category"] in CATEGORIES else "other"
        if "media" in payload and payload["media"] is not None:
            payload["media"] = await self._normalize_media(user.id, body.media or [])
        if any(k in payload for k in ("fee_type", "fee_cents", "fee_note")):
            ft, cents, note = _normalize_fee(
                payload.get("fee_type", activity.fee_type),
                payload.get("fee_cents", activity.fee_cents),
                payload.get("fee_note", activity.fee_note),
            )
            payload["fee_type"] = ft
            payload["fee_cents"] = cents
            payload["fee_note"] = note
        for key, value in payload.items():
            if value is not None or key in ("fee_note", "description", "city", "address", "lat", "lng"):
                setattr(activity, key, value)
        if "capacity" in payload and activity.status == ActivityStatus.PUBLISHED.value:
            await self._promote_waitlist(activity)  # 扩容后候补自动递补
        # Host edits on published activity stay published; pending stays pending.
        await self.db.commit()
        await self.db.refresh(activity)
        return await self._brief(activity, viewer_id=user.id, include_members=False)

    async def cancel(self, user: User, activity_id: UUID, body: CancelActivityRequest) -> dict:
        from datetime import timezone

        activity = await self.db.get(Activity, activity_id)
        if activity is None:
            raise AppError(ErrorCodes.ACTIVITY_NOT_FOUND, "活动不存在", status_code=404)
        if activity.host_id != user.id:
            raise AppError(ErrorCodes.ACTIVITY_FORBIDDEN, "仅主办可取消", status_code=403)
        if activity.status == ActivityStatus.CANCELLED.value:
            return await self._brief(activity, viewer_id=user.id, include_members=False)
        activity.status = ActivityStatus.CANCELLED.value
        activity.cancel_reason = (body.reason or "").strip() or None
        activity.cancelled_at = datetime.now(timezone.utc)
        from app.modules.events.service import DomainEventName, DomainEventService

        await DomainEventService(self.db).enqueue(
            name=DomainEventName.ACTIVITY_CANCELLED,
            aggregate_kind="activity",
            aggregate_id=activity.id,
            payload={"host_id": str(activity.host_id), "reason": activity.cancel_reason or ""},
        )
        await self.db.commit()
        await self.db.refresh(activity)
        return await self._brief(activity, viewer_id=user.id, include_members=False)

    async def get_details(self, user: User, activity_id: UUID) -> dict:
        await self._get_visible(activity_id, user.id)
        detail = await self.db.get(ActivityDetail, activity_id)
        return self._details_brief(activity_id, detail)

    async def upsert_details(self, user: User, activity_id: UUID, body: ActivityDetailsRequest) -> dict:
        activity = await self.db.get(Activity, activity_id)
        if activity is None or activity.status == ActivityStatus.CANCELLED.value:
            raise AppError(ErrorCodes.ACTIVITY_NOT_FOUND, "活动不存在", status_code=404)
        if activity.host_id != user.id:
            raise AppError(ErrorCodes.ACTIVITY_FORBIDDEN, "仅主办可编辑详情", status_code=403)
        detail = await self.db.get(ActivityDetail, activity_id)
        if detail is None:
            detail = ActivityDetail(activity_id=activity_id)
            self.db.add(detail)
        payload = body.model_dump(exclude_unset=True)
        for key, value in payload.items():
            if value is not None or key == "host_note":
                setattr(detail, key, value if value is not None else ([] if key != "host_note" else None))
        await self.db.commit()
        await self.db.refresh(detail)
        return self._details_brief(activity_id, detail)

    def _details_brief(self, activity_id: UUID, detail: ActivityDetail | None) -> dict:
        if detail is None:
            return {
                "activity_id": activity_id,
                "timeline": [],
                "gear": [],
                "fee_included": [],
                "fee_excluded": [],
                "refund_notes": [],
                "prep_notes": [],
                "registration_notes": [],
                "host_note": None,
                "gallery": [],
            }
        return {
            "activity_id": activity_id,
            "timeline": detail.timeline or [],
            "gear": detail.gear or [],
            "fee_included": detail.fee_included or [],
            "fee_excluded": detail.fee_excluded or [],
            "refund_notes": detail.refund_notes or [],
            "prep_notes": detail.prep_notes or [],
            "registration_notes": detail.registration_notes or [],
            "host_note": detail.host_note,
            "gallery": detail.gallery or [],
            "updated_at": detail.updated_at.isoformat() if detail.updated_at else None,
        }

    async def favorite(self, user: User, activity_id: UUID) -> dict:
        activity = await self._get_published(activity_id)
        existing = await self.db.execute(
            select(ActivityFavorite).where(
                ActivityFavorite.activity_id == activity_id,
                ActivityFavorite.user_id == user.id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return {"favorited": True, "favorite_count": activity.favorite_count}
        self.db.add(ActivityFavorite(id=uuid4(), activity_id=activity_id, user_id=user.id))
        activity.favorite_count = int(activity.favorite_count or 0) + 1
        await self.db.commit()
        return {"favorited": True, "favorite_count": activity.favorite_count}

    async def unfavorite(self, user: User, activity_id: UUID) -> dict:
        activity = await self._get_published(activity_id)
        result = await self.db.execute(
            select(ActivityFavorite).where(
                ActivityFavorite.activity_id == activity_id,
                ActivityFavorite.user_id == user.id,
            )
        )
        row = result.scalar_one_or_none()
        if row is not None:
            await self.db.delete(row)
            activity.favorite_count = max(int(activity.favorite_count or 0) - 1, 0)
            await self.db.commit()
        return {"favorited": False, "favorite_count": activity.favorite_count}

    async def search(
        self,
        user: User,
        *,
        q: str | None,
        city: str | None,
        category: str | None,
        fee_type: str | None,
        free_only: bool,
        limit: int,
        offset: int,
    ) -> dict:
        from sqlalchemy import or_

        stmt = (
            select(Activity)
            .where(Activity.status == ActivityStatus.PUBLISHED.value)
            .order_by(Activity.start_at.asc().nullslast(), Activity.created_at.desc())
        )
        if q:
            like = f"%{q.strip()}%"
            stmt = stmt.where(or_(Activity.title.ilike(like), Activity.description.ilike(like)))
        if city:
            stmt = stmt.where(Activity.city == city)
        if category:
            stmt = stmt.where(Activity.category == category)
        if free_only:
            stmt = stmt.where(Activity.fee_type == FeeType.FREE.value)
        elif fee_type and fee_type in FEE_TYPES:
            stmt = stmt.where(Activity.fee_type == fee_type)
        result = await self.db.execute(stmt.offset(offset).limit(limit))
        rows = list(result.scalars().all())
        items = [await self._brief(a, viewer_id=user.id, include_members=False) for a in rows]
        return {"items": items, "limit": limit, "offset": offset}

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
        favorited = await self._favorited(activity.id, viewer_id)
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
            "media": expose_media(activity.media or []),
            "fee_type": getattr(activity, "fee_type", None) or FeeType.FREE.value,
            "fee_cents": int(getattr(activity, "fee_cents", 0) or 0),
            "fee_note": getattr(activity, "fee_note", None),
            "status": activity.status,
            "like_count": activity.like_count,
            "comment_count": activity.comment_count,
            "favorite_count": int(getattr(activity, "favorite_count", 0) or 0),
            "liked": liked,
            "joined": joined,
            "favorited": favorited,
            "is_host": activity.host_id == viewer_id,
            "cancel_reason": getattr(activity, "cancel_reason", None),
            "cancelled_at": activity.cancelled_at.isoformat() if getattr(activity, "cancelled_at", None) else None,
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
