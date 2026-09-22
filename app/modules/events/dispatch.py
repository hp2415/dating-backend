"""Dispatch handlers for claimed domain events (extend per milestone)."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select, text

from app.models import (
    Activity,
    ActivityParticipant,
    CommunityPost,
    CompanionBooking,
    DomainEvent,
    NotificationCategory,
)
from app.modules.events.service import DomainEventName
from app.modules.ops.service import OpsService
from app.shared.db import SessionLocal

logger = logging.getLogger("dating.events")


async def dispatch_event(event: DomainEvent) -> None:
    """Route side effects. Keep handlers idempotent — worker may retry."""
    handlers = {
        DomainEventName.OPS_PING: _handle_ops_ping,
        DomainEventName.ACTIVITY_REVIEWED: _notify_activity_reviewed,
        DomainEventName.ACTIVITY_CANCELLED: _notify_activity_cancelled,
        DomainEventName.COMMUNITY_POST_REVIEWED: _notify_post_reviewed,
        DomainEventName.REPORT_RESOLVED: _handle_log_only,
        DomainEventName.MEDIA_REVIEWED: _handle_log_only,
        DomainEventName.ACTIVITY_JOINED: _handle_activity_joined,
        DomainEventName.MATCH_CREATED: _handle_log_only,
        DomainEventName.ORDER_PAID: _handle_log_only,
        DomainEventName.ORDER_CANCELLED: _handle_log_only,
        DomainEventName.ORDER_REFUNDED: _handle_log_only,
        DomainEventName.ORDER_EXPIRED: _handle_log_only,
        DomainEventName.CONVERSATION_CREATED: _handle_log_only,
        DomainEventName.FRIEND_REQUEST_SENT: _notify_friend_request,
        DomainEventName.COMPANION_REVIEWED: _notify_companion_reviewed,
        DomainEventName.BOOKING_CREATED: _notify_booking_created,
        DomainEventName.BOOKING_PAID: _notify_booking_paid,
        DomainEventName.BOOKING_COMPLETED: _notify_booking_completed,
        DomainEventName.BOOKING_CANCELLED: _notify_booking_cancelled,
        DomainEventName.BUDDY_INVITE_SENT: _notify_buddy_invite,
    }
    handler = handlers.get(event.name, _handle_log_only)
    await handler(event)


async def _handle_ops_ping(event: DomainEvent) -> None:
    logger.info("ops.ping processed id=%s payload=%s", event.id, event.payload)


async def _handle_log_only(event: DomainEvent) -> None:
    logger.info(
        "domain_event name=%s aggregate=%s/%s attempts=%s",
        event.name,
        event.aggregate_kind,
        event.aggregate_id,
        event.attempts,
    )


async def _handle_activity_joined(event: DomainEvent) -> None:
    """Ensure activity group membership (idempotent; join path already does this)."""
    await _handle_log_only(event)
    payload = event.payload or {}
    user_raw = payload.get("user_id")
    if not user_raw or not event.aggregate_id:
        return
    try:
        user_id = UUID(str(user_raw))
        activity_id = event.aggregate_id if isinstance(event.aggregate_id, UUID) else UUID(str(event.aggregate_id))
    except (TypeError, ValueError):
        return

    async with SessionLocal() as db:
        activity = await db.get(Activity, activity_id)
        if activity is None:
            return
        from app.modules.messaging.service import MessagingService

        await MessagingService(db).ensure_activity_group(activity, user_id)
        await db.commit()
        logger.info("activity.joined synced group activity=%s user=%s", activity_id, user_id)


async def _notify_activity_reviewed(event: DomainEvent) -> None:
    activity_id = _as_uuid(event.aggregate_id)
    if activity_id is None:
        return
    approved = str((event.payload or {}).get("action") or "") == "approve"
    async with SessionLocal() as db:
        activity = await db.get(Activity, activity_id)
        if activity is None:
            return
        title = "活动已通过" if approved else "活动未通过"
        body = activity.title or ""
        await _notify(
            db,
            event,
            user_id=activity.host_id,
            category=NotificationCategory.ACTIVITY.value,
            title=title,
            body=body,
            deep_link=f"spark://activity/{activity.id}",
            target_type="activity",
            target_id=str(activity.id),
        )
        await db.commit()


async def _notify_activity_cancelled(event: DomainEvent) -> None:
    activity_id = _as_uuid(event.aggregate_id)
    if activity_id is None:
        return
    reason = str((event.payload or {}).get("reason") or "")
    async with SessionLocal() as db:
        activity = await db.get(Activity, activity_id)
        if activity is None:
            return
        rows = await db.execute(
            select(ActivityParticipant.user_id).where(
                ActivityParticipant.activity_id == activity_id,
                ActivityParticipant.status == "joined",
                ActivityParticipant.user_id != activity.host_id,
            )
        )
        body = activity.title or ""
        if reason:
            body = f"{body} · {reason}"[:500]
        for (user_id,) in rows.all():
            await _notify(
                db,
                event,
                user_id=user_id,
                category=NotificationCategory.ACTIVITY.value,
                title="活动已取消",
                body=body,
                deep_link=f"spark://activity/{activity.id}",
                target_type="activity",
                target_id=str(activity.id),
            )
        await db.commit()


async def _notify_post_reviewed(event: DomainEvent) -> None:
    post_id = _as_uuid(event.aggregate_id)
    if post_id is None:
        return
    approved = str((event.payload or {}).get("action") or "") == "approve"
    async with SessionLocal() as db:
        post = await db.get(CommunityPost, post_id)
        if post is None:
            return
        await _notify(
            db,
            event,
            user_id=post.author_id,
            category=NotificationCategory.COMMUNITY.value,
            title="动态已通过" if approved else "动态未通过",
            body=(post.content or "")[:80],
            deep_link=f"spark://post/{post.id}",
            target_type="community_post",
            target_id=str(post.id),
        )
        await db.commit()


async def _notify_companion_reviewed(event: DomainEvent) -> None:
    user_id = _as_uuid(event.aggregate_id)
    if user_id is None:
        return
    approved = bool((event.payload or {}).get("approved"))
    async with SessionLocal() as db:
        await _notify(
            db,
            event,
            user_id=user_id,
            category=NotificationCategory.BOOKING.value,
            title="陪玩申请已通过" if approved else "陪玩申请未通过",
            body="可以去「成为陪玩」查看状态",
            deep_link="spark://companion",
            target_type="companion",
            target_id=str(user_id),
        )
        await db.commit()


async def _notify_friend_request(event: DomainEvent) -> None:
    target = _as_uuid((event.payload or {}).get("to"))
    if target is None:
        return
    async with SessionLocal() as db:
        await _notify(
            db,
            event,
            user_id=target,
            category=NotificationCategory.MESSAGE.value,
            title="新的好友申请",
            body="有人想加你为好友",
            deep_link="spark://friends",
            target_type="friend_request",
            target_id=str(event.aggregate_id or ""),
        )
        await db.commit()


async def _notify_buddy_invite(event: DomainEvent) -> None:
    payload = event.payload or {}
    target = _as_uuid(payload.get("to"))
    if target is None:
        return
    activity_id = str(payload.get("activity_id") or "")
    async with SessionLocal() as db:
        await _notify(
            db,
            event,
            user_id=target,
            category=NotificationCategory.BUDDY.value,
            title="新的活动邀约",
            body="有人邀请你一起参加活动",
            deep_link=f"spark://activity/{activity_id}" if activity_id else "spark://buddies",
            target_type="buddy_invite",
            target_id=str(event.aggregate_id or ""),
        )
        await db.commit()


async def _notify_booking_created(event: DomainEvent) -> None:
    await _notify_booking_party(
        event,
        user_key="companion_id",
        title="有新的陪玩预约",
        body="买家已下单，等待支付",
    )


async def _notify_booking_paid(event: DomainEvent) -> None:
    await _notify_booking_party(
        event,
        user_key="companion_id",
        title="预约已支付",
        body="买家已用余额支付，可以开始服务",
    )


async def _notify_booking_completed(event: DomainEvent) -> None:
    payload = event.payload or {}
    booking_id = str(event.aggregate_id or "")
    async with SessionLocal() as db:
        for key in ("buyer_id", "companion_id"):
            user_id = _as_uuid(payload.get(key))
            if user_id is None:
                continue
            await _notify(
                db,
                event,
                user_id=user_id,
                category=NotificationCategory.BOOKING.value,
                title="预约已完成",
                body="可以填写履约回访",
                deep_link=f"spark://booking/{booking_id}",
                target_type="booking",
                target_id=booking_id,
            )
        await db.commit()


async def _notify_booking_cancelled(event: DomainEvent) -> None:
    booking_id = _as_uuid(event.aggregate_id)
    if booking_id is None:
        return
    actor = str((event.payload or {}).get("by") or "")
    async with SessionLocal() as db:
        booking = await db.get(CompanionBooking, booking_id)
        if booking is None:
            return
        parties = [booking.buyer_id, booking.companion_id]
        for user_id in parties:
            if str(user_id) == actor:
                continue
            await _notify(
                db,
                event,
                user_id=user_id,
                category=NotificationCategory.BOOKING.value,
                title="预约已取消",
                body=booking.cancel_reason or "对方取消了预约",
                deep_link=f"spark://booking/{booking.id}",
                target_type="booking",
                target_id=str(booking.id),
            )
        await db.commit()


async def _notify_booking_party(event: DomainEvent, *, user_key: str, title: str, body: str) -> None:
    user_id = _as_uuid((event.payload or {}).get(user_key))
    booking_id = str(event.aggregate_id or "")
    if user_id is None:
        return
    async with SessionLocal() as db:
        await _notify(
            db,
            event,
            user_id=user_id,
            category=NotificationCategory.BOOKING.value,
            title=title,
            body=body,
            deep_link=f"spark://booking/{booking_id}",
            target_type="booking",
            target_id=booking_id,
        )
        await db.commit()


async def _notify(
    db,
    event: DomainEvent,
    *,
    user_id: UUID,
    category: str,
    title: str,
    body: str,
    deep_link: str,
    target_type: str,
    target_id: str,
) -> None:
    event_id = str(event.id)
    existing = await db.execute(
        text(
            """
            SELECT 1 FROM notifications
            WHERE user_id = CAST(:uid AS uuid)
              AND payload->>'event_id' = :eid
            LIMIT 1
            """
        ),
        {"uid": str(user_id), "eid": event_id},
    )
    if existing.first() is not None:
        return
    await OpsService(db).create_notification(
        user_id=user_id,
        category=category,
        title=title,
        body=body,
        deep_link=deep_link,
        payload={
            "event_id": event_id,
            "event_name": event.name,
            "target_type": target_type,
            "target_id": target_id,
        },
    )


def _as_uuid(value: Any) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if not value:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def handler_inventory() -> list[dict[str, Any]]:
    return [
        {"name": DomainEventName.OPS_PING, "status": "active"},
        {"name": DomainEventName.ACTIVITY_REVIEWED, "status": "notify"},
        {"name": DomainEventName.ACTIVITY_CANCELLED, "status": "notify"},
        {"name": DomainEventName.COMMUNITY_POST_REVIEWED, "status": "notify"},
        {"name": DomainEventName.REPORT_RESOLVED, "status": "log"},
        {"name": DomainEventName.MEDIA_REVIEWED, "status": "log"},
        {"name": DomainEventName.ACTIVITY_JOINED, "status": "activity_group"},
        {"name": DomainEventName.MATCH_CREATED, "status": "log"},
        {"name": DomainEventName.ORDER_PAID, "status": "log"},
        {"name": DomainEventName.ORDER_CANCELLED, "status": "log"},
        {"name": DomainEventName.ORDER_REFUNDED, "status": "log"},
        {"name": DomainEventName.CONVERSATION_CREATED, "status": "log"},
        {"name": DomainEventName.FRIEND_REQUEST_SENT, "status": "notify"},
        {"name": DomainEventName.COMPANION_REVIEWED, "status": "notify"},
        {"name": DomainEventName.BOOKING_CREATED, "status": "notify"},
        {"name": DomainEventName.BOOKING_PAID, "status": "notify"},
        {"name": DomainEventName.BOOKING_COMPLETED, "status": "notify"},
        {"name": DomainEventName.BOOKING_CANCELLED, "status": "notify"},
        {"name": DomainEventName.BUDDY_INVITE_SENT, "status": "notify"},
        {"name": DomainEventName.TRUST_EVENT_RECORDED, "status": "log"},
        {"name": DomainEventName.ANNOUNCEMENT_PUBLISHED, "status": "log"},
    ]
