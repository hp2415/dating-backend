"""Domain event outbox — align with iOS AppDomainEvent for async side effects."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DomainEvent, DomainEventStatus
from app.shared.config import settings


# Names aligned with dating-ios AppDomainEvent / TrustEventName roadmap
class DomainEventName:
    ACTIVITY_JOINED = "activity.joined"
    ACTIVITY_LEFT = "activity.left"
    ACTIVITY_PUBLISHED = "activity.published"
    ACTIVITY_CANCELLED = "activity.cancelled"
    ACTIVITY_UPDATED = "activity.updated"
    ACTIVITY_REVIEWED = "activity.reviewed"
    COMMUNITY_POST_PUBLISHED = "community.post_published"
    COMMUNITY_POST_REVIEWED = "community.post_reviewed"
    USER_BLOCKED = "user.blocked"
    USER_UNBLOCKED = "user.unblocked"
    REPORT_RESOLVED = "report.resolved"
    MEDIA_REVIEWED = "media.reviewed"
    PROFILE_UPDATED = "profile.updated"
    MATCH_CREATED = "match.created"
    OPS_PING = "ops.ping"
    ORDER_PAID = "order.paid"
    ORDER_CANCELLED = "order.cancelled"
    ORDER_REFUNDED = "order.refunded"
    ORDER_EXPIRED = "order.expired"
    CONVERSATION_CREATED = "conversation.created"
    FRIEND_REQUEST_SENT = "friend.request_sent"
    # M6 companion / buddy
    COMPANION_APPLIED = "companion.applied"
    COMPANION_REVIEWED = "companion.reviewed"
    BOOKING_CREATED = "booking.created"
    BOOKING_PAID = "booking.paid"
    BOOKING_COMPLETED = "booking.completed"
    BOOKING_CANCELLED = "booking.cancelled"
    BUDDY_GREETING_SENT = "buddy.greeting_sent"
    BUDDY_INVITE_SENT = "buddy.invite_sent"
    # M7 trust
    TRUST_EVENT_RECORDED = "trust.event_recorded"
    VERIFICATION_SUBMITTED = "verification.submitted"
    VERIFICATION_REVIEWED = "verification.reviewed"
    SANCTION_APPLIED = "sanction.applied"
    # M8 ops
    PUSH_CAMPAIGN_SENT = "push.campaign_sent"
    ANNOUNCEMENT_PUBLISHED = "announcement.published"


class DomainEventService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def enqueue(
        self,
        *,
        name: str,
        aggregate_kind: str,
        aggregate_id: str | UUID,
        payload: dict[str, Any] | None = None,
        available_at: datetime | None = None,
    ) -> DomainEvent:
        event = DomainEvent(
            id=uuid4(),
            name=name,
            aggregate_kind=aggregate_kind,
            aggregate_id=str(aggregate_id),
            payload=payload or {},
            status=DomainEventStatus.PENDING.value,
            attempts=0,
            available_at=available_at or datetime.now(timezone.utc),
        )
        self.db.add(event)
        await self.db.flush()
        return event

    async def list_recent(self, *, limit: int = 20, offset: int = 0, status: str | None = None) -> tuple[list[DomainEvent], int]:
        filters = []
        if status:
            filters.append(DomainEvent.status == status)
        count_q = select(func.count()).select_from(DomainEvent)
        list_q = select(DomainEvent).order_by(DomainEvent.created_at.desc())
        if filters:
            for f in filters:
                count_q = count_q.where(f)
                list_q = list_q.where(f)
        total = int((await self.db.execute(count_q)).scalar_one())
        result = await self.db.execute(list_q.limit(limit).offset(offset))
        return list(result.scalars().all()), total

    async def claim_batch(self, *, limit: int | None = None) -> list[DomainEvent]:
        """Atomically claim pending events for this worker."""
        batch = limit or settings.domain_event_batch_size
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(DomainEvent)
            .where(
                DomainEvent.status == DomainEventStatus.PENDING.value,
                DomainEvent.available_at <= now,
            )
            .order_by(DomainEvent.available_at.asc())
            .limit(batch)
            .with_for_update(skip_locked=True)
        )
        events = list(result.scalars().all())
        for event in events:
            event.status = DomainEventStatus.PROCESSING.value
            event.attempts += 1
        await self.db.flush()
        return events

    async def mark_done(self, event: DomainEvent) -> None:
        event.status = DomainEventStatus.DONE.value
        event.processed_at = datetime.now(timezone.utc)
        event.last_error = None
        await self.db.flush()

    async def mark_failed(self, event: DomainEvent, error: str, *, retry: bool = True) -> None:
        if retry and event.attempts < 8:
            # Exponential backoff: 15s, 30s, 60s, …
            delay = min(3600, 15 * (2 ** max(0, event.attempts - 1)))
            event.status = DomainEventStatus.PENDING.value
            event.available_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
            event.last_error = error[:2000]
        else:
            event.status = DomainEventStatus.FAILED.value
            event.last_error = error[:2000]
            event.processed_at = datetime.now(timezone.utc)
        await self.db.flush()


def event_to_dict(event: DomainEvent) -> dict[str, Any]:
    return {
        "id": str(event.id),
        "name": event.name,
        "aggregate_kind": event.aggregate_kind,
        "aggregate_id": event.aggregate_id,
        "payload": event.payload,
        "status": event.status,
        "attempts": event.attempts,
        "last_error": event.last_error,
        "available_at": event.available_at.isoformat() if event.available_at else None,
        "processed_at": event.processed_at.isoformat() if event.processed_at else None,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }
