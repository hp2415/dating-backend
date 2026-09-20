"""Ops / config service: taxonomies, shelves, notifications, campaigns."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Announcement,
    AnnouncementStatus,
    CampaignStatus,
    DiscoverShelf,
    DiscoverShelfItem,
    Feedback,
    FeedbackStatus,
    Notification,
    NotificationCategory,
    PushCampaign,
    PushToken,
    ShelfLayout,
    ShelfRuleType,
    Taxonomy,
    User,
)
from app.modules.events.service import DomainEventName, DomainEventService
from app.modules.ops.schemas import (
    AnnouncementCreate,
    CampaignCreate,
    FeedbackCreate,
    FeedbackReply,
    PushTokenRegister,
    ShelfItemUpsert,
    ShelfUpsert,
    TaxonomyUpsert,
)
from app.shared.errors import AppError
from app.shared.response import ErrorCodes


class OpsService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.events = DomainEventService(db)

    # ── taxonomies ─────────────────────────────────────────

    async def list_taxonomies(
        self, *, kind: str | None = None, enabled_only: bool = True
    ) -> list[dict]:
        filters = []
        if kind:
            filters.append(Taxonomy.kind == kind)
        if enabled_only:
            filters.append(Taxonomy.enabled.is_(True))
        stmt = select(Taxonomy).order_by(
            Taxonomy.kind.asc(), Taxonomy.sort_order.asc(), Taxonomy.code.asc()
        )
        for f in filters:
            stmt = stmt.where(f)
        rows = list((await self.db.execute(stmt)).scalars().all())
        return [self.taxonomy_brief(r) for r in rows]

    async def upsert_taxonomy(self, body: TaxonomyUpsert, *, taxonomy_id: UUID | None = None) -> dict:
        kind = (body.kind or "").strip()
        code = (body.code or "").strip()
        name = (body.name or "").strip()
        if not kind or not code or not name:
            raise AppError(ErrorCodes.TAXONOMY_INVALID, "kind/code/name 必填")
        row: Taxonomy | None = None
        if taxonomy_id is not None:
            row = await self.db.get(Taxonomy, taxonomy_id)
            if row is None:
                raise AppError(ErrorCodes.OPS_NOT_FOUND, "分类不存在", status_code=404)
        else:
            hit = await self.db.execute(
                select(Taxonomy).where(Taxonomy.kind == kind, Taxonomy.code == code)
            )
            row = hit.scalar_one_or_none()
        if row is None:
            row = Taxonomy(id=uuid4(), kind=kind, code=code)
            self.db.add(row)
        row.kind = kind
        row.code = code
        row.name = name
        row.parent_code = body.parent_code
        row.icon = body.icon
        row.sort_order = body.sort_order
        row.enabled = body.enabled
        row.meta = body.meta or {}
        await self.db.flush()
        return self.taxonomy_brief(row)

    async def delete_taxonomy(self, taxonomy_id: UUID) -> dict:
        row = await self.db.get(Taxonomy, taxonomy_id)
        if row is None:
            raise AppError(ErrorCodes.OPS_NOT_FOUND, "分类不存在", status_code=404)
        brief = self.taxonomy_brief(row)
        await self.db.delete(row)
        await self.db.flush()
        return brief

    @staticmethod
    def taxonomy_brief(row: Taxonomy) -> dict:
        return {
            "id": str(row.id),
            "kind": row.kind,
            "code": row.code,
            "parent_code": row.parent_code,
            "name": row.name,
            "icon": row.icon,
            "sort_order": row.sort_order,
            "enabled": row.enabled,
            "meta": row.meta or {},
        }

    # ── discover shelves ───────────────────────────────────

    async def list_active_shelves(self, *, city: str | None = None) -> list[dict]:
        now = datetime.now(timezone.utc)
        filters = [
            DiscoverShelf.enabled.is_(True),
            or_(DiscoverShelf.starts_at.is_(None), DiscoverShelf.starts_at <= now),
            or_(DiscoverShelf.ends_at.is_(None), DiscoverShelf.ends_at >= now),
        ]
        stmt = (
            select(DiscoverShelf)
            .where(*filters)
            .order_by(DiscoverShelf.sort_order.asc(), DiscoverShelf.created_at.desc())
        )
        rows = list((await self.db.execute(stmt)).scalars().all())
        out: list[dict] = []
        for shelf in rows:
            scope = list(shelf.city_scope or [])
            if city and scope and city not in scope:
                continue
            items = await self._shelf_items(shelf.id)
            out.append(self.shelf_brief(shelf, items=items))
        return out

    async def list_shelves_admin(
        self, *, limit: int = 50, offset: int = 0, enabled: bool | None = None
    ) -> tuple[list[dict], int]:
        filters = []
        if enabled is not None:
            filters.append(DiscoverShelf.enabled.is_(enabled))
        count_q = select(func.count()).select_from(DiscoverShelf)
        list_q = select(DiscoverShelf).order_by(
            DiscoverShelf.sort_order.asc(), DiscoverShelf.created_at.desc()
        )
        for f in filters:
            count_q = count_q.where(f)
            list_q = list_q.where(f)
        total = int((await self.db.execute(count_q)).scalar_one())
        rows = list((await self.db.execute(list_q.limit(limit).offset(offset))).scalars().all())
        items = []
        for shelf in rows:
            shelf_items = await self._shelf_items(shelf.id)
            items.append(self.shelf_brief(shelf, items=shelf_items))
        return items, total

    async def upsert_shelf(self, body: ShelfUpsert, *, shelf_id: UUID | None = None) -> dict:
        title = (body.title or "").strip()
        if not title:
            raise AppError(ErrorCodes.OPS_INVALID, "title 必填")
        row: DiscoverShelf | None = None
        if shelf_id is not None:
            row = await self.db.get(DiscoverShelf, shelf_id)
            if row is None:
                raise AppError(ErrorCodes.OPS_NOT_FOUND, "货架不存在", status_code=404)
        if row is None:
            row = DiscoverShelf(id=uuid4())
            self.db.add(row)
        row.title = title
        row.subtitle = (body.subtitle or "")[:160]
        row.layout = body.layout or ShelfLayout.RAIL.value
        row.rule_type = body.rule_type or ShelfRuleType.MANUAL.value
        row.rule = body.rule or {}
        row.city_scope = list(body.city_scope or [])
        row.sort_order = body.sort_order
        row.enabled = body.enabled
        row.starts_at = body.starts_at
        row.ends_at = body.ends_at
        await self.db.flush()
        items = await self._shelf_items(row.id)
        return self.shelf_brief(row, items=items)

    async def delete_shelf(self, shelf_id: UUID) -> dict:
        row = await self.db.get(DiscoverShelf, shelf_id)
        if row is None:
            raise AppError(ErrorCodes.OPS_NOT_FOUND, "货架不存在", status_code=404)
        brief = self.shelf_brief(row)
        await self.db.delete(row)
        await self.db.flush()
        return brief

    async def upsert_shelf_item(
        self, shelf_id: UUID, body: ShelfItemUpsert, *, item_id: UUID | None = None
    ) -> dict:
        shelf = await self.db.get(DiscoverShelf, shelf_id)
        if shelf is None:
            raise AppError(ErrorCodes.OPS_NOT_FOUND, "货架不存在", status_code=404)
        row: DiscoverShelfItem | None = None
        if item_id is not None:
            row = await self.db.get(DiscoverShelfItem, item_id)
            if row is None or row.shelf_id != shelf_id:
                raise AppError(ErrorCodes.OPS_NOT_FOUND, "货架条目不存在", status_code=404)
        if row is None:
            row = DiscoverShelfItem(id=uuid4(), shelf_id=shelf_id)
            self.db.add(row)
        row.subject_kind = body.subject_kind
        row.subject_id = body.subject_id
        row.sort_order = body.sort_order
        row.pinned = body.pinned
        await self.db.flush()
        return self.shelf_item_brief(row)

    async def delete_shelf_item(self, shelf_id: UUID, item_id: UUID) -> dict:
        row = await self.db.get(DiscoverShelfItem, item_id)
        if row is None or row.shelf_id != shelf_id:
            raise AppError(ErrorCodes.OPS_NOT_FOUND, "货架条目不存在", status_code=404)
        brief = self.shelf_item_brief(row)
        await self.db.delete(row)
        await self.db.flush()
        return brief

    async def list_shelf_items(self, shelf_id: UUID) -> list[dict]:
        shelf = await self.db.get(DiscoverShelf, shelf_id)
        if shelf is None:
            raise AppError(ErrorCodes.OPS_NOT_FOUND, "货架不存在", status_code=404)
        return await self._shelf_items(shelf_id)

    async def _shelf_items(self, shelf_id: UUID) -> list[dict]:
        rows = list(
            (
                await self.db.execute(
                    select(DiscoverShelfItem)
                    .where(DiscoverShelfItem.shelf_id == shelf_id)
                    .order_by(
                        DiscoverShelfItem.pinned.desc(),
                        DiscoverShelfItem.sort_order.asc(),
                    )
                )
            )
            .scalars()
            .all()
        )
        return [self.shelf_item_brief(r) for r in rows]

    @staticmethod
    def shelf_brief(row: DiscoverShelf, *, items: list[dict] | None = None) -> dict:
        data = {
            "id": str(row.id),
            "title": row.title,
            "subtitle": row.subtitle,
            "layout": row.layout,
            "rule_type": row.rule_type,
            "rule": row.rule or {},
            "city_scope": list(row.city_scope or []),
            "sort_order": row.sort_order,
            "enabled": row.enabled,
            "starts_at": row.starts_at.isoformat() if row.starts_at else None,
            "ends_at": row.ends_at.isoformat() if row.ends_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        if items is not None:
            data["items"] = items
        return data

    @staticmethod
    def shelf_item_brief(row: DiscoverShelfItem) -> dict:
        return {
            "id": str(row.id),
            "shelf_id": str(row.shelf_id),
            "subject_kind": row.subject_kind,
            "subject_id": str(row.subject_id),
            "sort_order": row.sort_order,
            "pinned": row.pinned,
        }

    # ── push tokens ────────────────────────────────────────

    async def register_push_token(self, user: User, body: PushTokenRegister) -> dict:
        device_id = (body.device_id or "").strip()
        token = (body.token or "").strip()
        if not device_id or not token:
            raise AppError(ErrorCodes.OPS_INVALID, "device_id/token 必填")
        hit = await self.db.execute(
            select(PushToken).where(
                PushToken.user_id == user.id, PushToken.device_id == device_id
            )
        )
        row = hit.scalar_one_or_none()
        if row is None:
            row = PushToken(id=uuid4(), user_id=user.id, device_id=device_id)
            self.db.add(row)
        row.platform = body.platform
        row.provider = body.provider or "fcm"
        row.token = token
        row.active = True
        await self.db.flush()
        return {
            "id": str(row.id),
            "device_id": row.device_id,
            "platform": row.platform,
            "provider": row.provider,
            "active": row.active,
        }

    # ── notifications ──────────────────────────────────────

    async def create_notification(
        self,
        *,
        user_id: UUID,
        title: str,
        body: str = "",
        category: str = NotificationCategory.SYSTEM.value,
        deep_link: str | None = None,
        payload: dict | None = None,
    ) -> Notification:
        row = Notification(
            id=uuid4(),
            user_id=user_id,
            category=category,
            title=(title or "")[:120],
            body=(body or "")[:500],
            deep_link=deep_link,
            payload=payload or {},
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def list_notifications(
        self, user_id: UUID, *, limit: int = 20, offset: int = 0, unread_only: bool = False
    ) -> tuple[list[dict], int]:
        filters = [Notification.user_id == user_id]
        if unread_only:
            filters.append(Notification.read_at.is_(None))
        count_q = select(func.count()).select_from(Notification).where(*filters)
        total = int((await self.db.execute(count_q)).scalar_one())
        rows = list(
            (
                await self.db.execute(
                    select(Notification)
                    .where(*filters)
                    .order_by(Notification.created_at.desc())
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return [self.notification_brief(r) for r in rows], total

    async def mark_notifications_read(
        self, user_id: UUID, *, ids: list[UUID] | None = None, mark_all: bool = False
    ) -> dict:
        if not mark_all and not ids:
            raise AppError(ErrorCodes.OPS_INVALID, "须指定 ids 或 all=true")
        now = datetime.now(timezone.utc)
        filters = [
            Notification.user_id == user_id,
            Notification.read_at.is_(None),
        ]
        if not mark_all:
            filters.append(Notification.id.in_(ids or []))
        result = await self.db.execute(
            update(Notification).where(and_(*filters)).values(read_at=now)
        )
        await self.db.flush()
        return {"marked": int(result.rowcount or 0)}

    @staticmethod
    def notification_brief(row: Notification) -> dict:
        return {
            "id": str(row.id),
            "category": row.category,
            "title": row.title,
            "body": row.body,
            "deep_link": row.deep_link,
            "payload": row.payload or {},
            "read_at": row.read_at.isoformat() if row.read_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    # ── announcements ──────────────────────────────────────

    async def list_announcements(
        self, *, published_only: bool = True, limit: int = 20, offset: int = 0
    ) -> tuple[list[dict], int]:
        now = datetime.now(timezone.utc)
        filters = []
        if published_only:
            filters.append(Announcement.status == AnnouncementStatus.PUBLISHED.value)
            filters.append(or_(Announcement.publish_at.is_(None), Announcement.publish_at <= now))
            filters.append(or_(Announcement.expire_at.is_(None), Announcement.expire_at >= now))
        count_q = select(func.count()).select_from(Announcement)
        list_q = select(Announcement).order_by(
            Announcement.pinned.desc(), Announcement.created_at.desc()
        )
        for f in filters:
            count_q = count_q.where(f)
            list_q = list_q.where(f)
        total = int((await self.db.execute(count_q)).scalar_one())
        rows = list((await self.db.execute(list_q.limit(limit).offset(offset))).scalars().all())
        return [self.announcement_brief(r) for r in rows], total

    async def create_announcement(self, body: AnnouncementCreate, *, admin_id: UUID | None) -> dict:
        title = (body.title or "").strip()
        if not title:
            raise AppError(ErrorCodes.OPS_INVALID, "title 必填")
        row = Announcement(
            id=uuid4(),
            title=title,
            body=body.body or "",
            pinned=body.pinned,
            audience=body.audience or "all",
            publish_at=body.publish_at,
            expire_at=body.expire_at,
            status=AnnouncementStatus.DRAFT.value,
            created_by=admin_id,
        )
        self.db.add(row)
        await self.db.flush()
        return self.announcement_brief(row)

    async def publish_announcement(self, announcement_id: UUID) -> dict:
        row = await self.db.get(Announcement, announcement_id)
        if row is None:
            raise AppError(ErrorCodes.OPS_NOT_FOUND, "公告不存在", status_code=404)
        row.status = AnnouncementStatus.PUBLISHED.value
        if row.publish_at is None:
            row.publish_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.events.enqueue(
            name=DomainEventName.ANNOUNCEMENT_PUBLISHED,
            aggregate_kind="announcement",
            aggregate_id=row.id,
            payload={"title": row.title, "audience": row.audience},
        )
        return self.announcement_brief(row)

    @staticmethod
    def announcement_brief(row: Announcement) -> dict:
        return {
            "id": str(row.id),
            "title": row.title,
            "body": row.body,
            "pinned": row.pinned,
            "audience": row.audience,
            "publish_at": row.publish_at.isoformat() if row.publish_at else None,
            "expire_at": row.expire_at.isoformat() if row.expire_at else None,
            "status": row.status,
            "created_by": str(row.created_by) if row.created_by else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    # ── feedback ───────────────────────────────────────────

    async def create_feedback(self, user: User, body: FeedbackCreate) -> dict:
        content = (body.content or "").strip()
        if not content:
            raise AppError(ErrorCodes.OPS_INVALID, "content 必填")
        row = Feedback(
            id=uuid4(),
            user_id=user.id,
            category=(body.category or "general")[:32],
            content=content,
            contact=body.contact,
            status=FeedbackStatus.OPEN.value,
        )
        self.db.add(row)
        await self.db.flush()
        return self.feedback_brief(row)

    async def list_feedbacks(
        self, *, status: str | None = None, limit: int = 20, offset: int = 0
    ) -> tuple[list[dict], int]:
        filters = []
        if status:
            filters.append(Feedback.status == status)
        count_q = select(func.count()).select_from(Feedback)
        list_q = select(Feedback).order_by(Feedback.created_at.desc())
        for f in filters:
            count_q = count_q.where(f)
            list_q = list_q.where(f)
        total = int((await self.db.execute(count_q)).scalar_one())
        rows = list((await self.db.execute(list_q.limit(limit).offset(offset))).scalars().all())
        return [self.feedback_brief(r) for r in rows], total

    async def reply_feedback(self, feedback_id: UUID, body: FeedbackReply) -> dict:
        row = await self.db.get(Feedback, feedback_id)
        if row is None:
            raise AppError(ErrorCodes.OPS_NOT_FOUND, "反馈不存在", status_code=404)
        reply = (body.reply or "").strip()
        if not reply:
            raise AppError(ErrorCodes.OPS_INVALID, "reply 必填")
        row.admin_reply = reply
        row.replied_at = datetime.now(timezone.utc)
        row.status = FeedbackStatus.REPLIED.value
        await self.db.flush()
        await self.create_notification(
            user_id=row.user_id,
            title="反馈已回复",
            body=reply[:200],
            category=NotificationCategory.SYSTEM.value,
            payload={"feedback_id": str(row.id)},
        )
        return self.feedback_brief(row)

    @staticmethod
    def feedback_brief(row: Feedback) -> dict:
        return {
            "id": str(row.id),
            "user_id": str(row.user_id),
            "category": row.category,
            "content": row.content,
            "contact": row.contact,
            "status": row.status,
            "admin_reply": row.admin_reply,
            "replied_at": row.replied_at.isoformat() if row.replied_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    # ── push campaigns ─────────────────────────────────────

    async def create_campaign(self, body: CampaignCreate, *, admin_id: UUID | None) -> dict:
        title = (body.title or "").strip()
        if not title:
            raise AppError(ErrorCodes.OPS_INVALID, "title 必填")
        row = PushCampaign(
            id=uuid4(),
            title=title,
            body=body.body or "",
            deep_link=body.deep_link,
            audience=body.audience or {},
            scheduled_at=body.scheduled_at,
            status=CampaignStatus.DRAFT.value,
            created_by=admin_id,
        )
        self.db.add(row)
        await self.db.flush()
        return self.campaign_brief(row)

    async def list_campaigns(
        self, *, status: str | None = None, limit: int = 20, offset: int = 0
    ) -> tuple[list[dict], int]:
        filters = []
        if status:
            filters.append(PushCampaign.status == status)
        count_q = select(func.count()).select_from(PushCampaign)
        list_q = select(PushCampaign).order_by(PushCampaign.created_at.desc())
        for f in filters:
            count_q = count_q.where(f)
            list_q = list_q.where(f)
        total = int((await self.db.execute(count_q)).scalar_one())
        rows = list((await self.db.execute(list_q.limit(limit).offset(offset))).scalars().all())
        return [self.campaign_brief(r) for r in rows], total

    async def send_campaign(
        self, campaign_id: UUID, *, audience_override: dict | None = None
    ) -> dict:
        row = await self.db.get(PushCampaign, campaign_id)
        if row is None:
            raise AppError(ErrorCodes.OPS_NOT_FOUND, "推送计划不存在", status_code=404)
        if row.status == CampaignStatus.SENT.value:
            raise AppError(ErrorCodes.OPS_INVALID, "推送已发送")
        audience = audience_override if audience_override is not None else (row.audience or {})
        user_ids = await self._resolve_campaign_audience(audience)
        row.status = CampaignStatus.SENDING.value
        sent = 0
        for uid in user_ids:
            await self.create_notification(
                user_id=uid,
                title=row.title,
                body=row.body,
                category=NotificationCategory.SYSTEM.value,
                deep_link=row.deep_link,
                payload={"campaign_id": str(row.id)},
            )
            sent += 1
        row.status = CampaignStatus.SENT.value
        row.sent_count = sent
        if audience_override is not None:
            row.audience = audience_override
        await self.db.flush()
        await self.events.enqueue(
            name=DomainEventName.PUSH_CAMPAIGN_SENT,
            aggregate_kind="push_campaign",
            aggregate_id=row.id,
            payload={"sent_count": sent, "title": row.title},
        )
        return self.campaign_brief(row)

    async def _resolve_campaign_audience(self, audience: dict) -> list[UUID]:
        raw_ids = audience.get("user_ids") if isinstance(audience, dict) else None
        if raw_ids:
            out: list[UUID] = []
            for item in raw_ids[:100]:
                try:
                    out.append(UUID(str(item)))
                except (TypeError, ValueError):
                    continue
            return out
        rows = list(
            (
                await self.db.execute(
                    select(User.id).order_by(User.created_at.desc()).limit(100)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    @staticmethod
    def campaign_brief(row: PushCampaign) -> dict:
        return {
            "id": str(row.id),
            "title": row.title,
            "body": row.body,
            "deep_link": row.deep_link,
            "audience": row.audience or {},
            "scheduled_at": row.scheduled_at.isoformat() if row.scheduled_at else None,
            "status": row.status,
            "sent_count": row.sent_count,
            "open_count": row.open_count,
            "created_by": str(row.created_by) if row.created_by else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
