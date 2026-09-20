"""Dispatch handlers for claimed domain events (extend per milestone)."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.models import Activity, DomainEvent
from app.modules.events.service import DomainEventName
from app.shared.db import SessionLocal

logger = logging.getLogger("dating.events")


async def dispatch_event(event: DomainEvent) -> None:
    """Route side effects. Keep handlers idempotent — worker may retry."""
    handlers = {
        DomainEventName.OPS_PING: _handle_ops_ping,
        DomainEventName.ACTIVITY_REVIEWED: _handle_log_only,
        DomainEventName.COMMUNITY_POST_REVIEWED: _handle_log_only,
        DomainEventName.REPORT_RESOLVED: _handle_log_only,
        DomainEventName.MEDIA_REVIEWED: _handle_log_only,
        DomainEventName.ACTIVITY_JOINED: _handle_activity_joined,
        DomainEventName.MATCH_CREATED: _handle_log_only,
        DomainEventName.ORDER_PAID: _handle_log_only,
        DomainEventName.ORDER_CANCELLED: _handle_log_only,
        DomainEventName.ORDER_REFUNDED: _handle_log_only,
        DomainEventName.ORDER_EXPIRED: _handle_log_only,
        DomainEventName.CONVERSATION_CREATED: _handle_log_only,
        DomainEventName.FRIEND_REQUEST_SENT: _handle_log_only,
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


def handler_inventory() -> list[dict[str, Any]]:
    return [
        {"name": DomainEventName.OPS_PING, "status": "active"},
        {"name": DomainEventName.ACTIVITY_REVIEWED, "status": "log"},
        {"name": DomainEventName.COMMUNITY_POST_REVIEWED, "status": "log"},
        {"name": DomainEventName.REPORT_RESOLVED, "status": "log"},
        {"name": DomainEventName.MEDIA_REVIEWED, "status": "log"},
        {"name": DomainEventName.ACTIVITY_JOINED, "status": "activity_group"},
        {"name": DomainEventName.MATCH_CREATED, "status": "stub_notify"},
        {"name": DomainEventName.ORDER_PAID, "status": "log"},
        {"name": DomainEventName.ORDER_CANCELLED, "status": "log"},
        {"name": DomainEventName.ORDER_REFUNDED, "status": "log"},
        {"name": DomainEventName.CONVERSATION_CREATED, "status": "stub_notify"},
        {"name": DomainEventName.FRIEND_REQUEST_SENT, "status": "stub_notify"},
        {"name": DomainEventName.BOOKING_CREATED, "status": "log"},
        {"name": DomainEventName.BOOKING_PAID, "status": "log"},
        {"name": DomainEventName.TRUST_EVENT_RECORDED, "status": "log"},
        {"name": DomainEventName.ANNOUNCEMENT_PUBLISHED, "status": "stub_notify"},
    ]
