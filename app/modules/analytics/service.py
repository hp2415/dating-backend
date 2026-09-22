"""Accept client analytics batches. Dedupe by event_id; never trust client IP or city."""

from __future__ import annotations

import hashlib
import json
import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.modules.analytics.schemas import AnalyticsBatchIn
from app.shared.errors import AppError
from app.shared.response import ErrorCodes

logger = logging.getLogger(__name__)

_KNOWN_EVENTS = {
    "app.launched",
    "app.foregrounded",
    "app.backgrounded",
    "auth.login_viewed",
    "auth.sms_requested",
    "auth.login_succeeded",
    "auth.login_failed",
    "auth.onboarding_completed",
    "auth.logged_out",
    "activity.feed_viewed",
    "activity.card_clicked",
    "activity.detail_viewed",
    "activity.join_clicked",
    "activity.join_succeeded",
    "activity.join_failed",
    "activity.favorited",
    "activity.compose_opened",
    "activity.published",
    "activity.cancelled",
    "buddy.feed_viewed",
    "buddy.detail_viewed",
    "buddy.greet_sent",
    "buddy.invite_sent",
    "buddy.invite_responded",
    "community.feed_viewed",
    "community.post_viewed",
    "community.post_liked",
    "community.compose_opened",
    "community.post_published",
    "message.inbox_viewed",
    "message.conversation_opened",
    "message.sent",
    "safety.report_submitted",
    "safety.block_submitted",
    "companion.list_viewed",
    "companion.detail_viewed",
    "companion.slot_selected",
    "companion.booking_created",
    "companion.booking_completed",
    "companion.review_submitted",
    "commerce.order_created",
    "commerce.pay_method_selected",
    "commerce.pay_succeeded",
    "commerce.pay_failed",
    "trust.safety_checkin_submitted",
    "error.api_failed",
}

_MAX_PROPS_BYTES = 4096


def hash_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()


class AnalyticsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def ingest(
        self,
        body: AnalyticsBatchIn,
        *,
        user: User | None,
        client_ip: str | None,
    ) -> dict:
        ip_hash = hash_ip(client_ip)
        user_id: UUID | None = user.id if user is not None else None
        accepted = 0
        duplicated = 0
        for event in body.events:
            encoded = json.dumps(event.props, ensure_ascii=False, default=str)
            if len(encoded.encode("utf-8")) > _MAX_PROPS_BYTES:
                raise AppError(ErrorCodes.AUTH_INVALID, "事件参数过大")
            if event.event_name not in _KNOWN_EVENTS:
                logger.warning("analytics unknown event_name=%s", event.event_name)

            inserted = await self.db.execute(
                text(
                    """
                    INSERT INTO analytics_event_dedupe (event_id)
                    VALUES (CAST(:event_id AS uuid))
                    ON CONFLICT (event_id) DO NOTHING
                    RETURNING event_id
                    """
                ),
                {"event_id": str(event.event_id)},
            )
            if inserted.first() is None:
                duplicated += 1
                continue

            await self.db.execute(
                text(
                    """
                    INSERT INTO analytics_events (
                        event_id, event_name, user_id, anon_id, session_id,
                        screen, referrer_screen, props, platform, app_version,
                        build_type, os_version, device_model, network_type,
                        city, ip_hash, occurred_at
                    ) VALUES (
                        CAST(:event_id AS uuid), :event_name, :user_id, :anon_id, :session_id,
                        :screen, :referrer_screen, CAST(:props AS jsonb), :platform, :app_version,
                        :build_type, :os_version, :device_model, :network_type,
                        NULL, :ip_hash, :occurred_at
                    )
                    """
                ),
                {
                    "event_id": str(event.event_id),
                    "event_name": event.event_name,
                    "user_id": user_id,
                    "anon_id": event.anon_id,
                    "session_id": event.session_id,
                    "screen": event.screen,
                    "referrer_screen": event.referrer_screen,
                    "props": encoded,
                    "platform": event.platform,
                    "app_version": event.app_version,
                    "build_type": event.build_type,
                    "os_version": event.os_version,
                    "device_model": event.device_model,
                    "network_type": event.network_type,
                    "ip_hash": ip_hash,
                    "occurred_at": event.occurred_at,
                },
            )
            accepted += 1
        await self.db.commit()
        return {"accepted": accepted, "duplicated": duplicated}
