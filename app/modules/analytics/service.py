"""Accept client analytics batches.

Guarantees: per-event validation (one bad event never poisons the batch), ``event_id`` idempotency,
PII scrubbing of props, device-clock-skew correction, never trusting client IP/city.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.modules.analytics.schemas import AnalyticsBatchIn, AnalyticsEventIn
from app.modules.analytics.taxonomy import (
    EVENT_NAME_RE,
    EVENTS,
    MIN_SUPPORTED_SCHEMA,
    PER_EVENT_SAMPLE,
    PROP_KEY_RE,
    SCHEMA_VERSION,
    event_object_type,
    is_pii_key,
    scrub_value,
)
from app.shared.config import settings
from app.shared.errors import AppError
from app.shared.response import ErrorCodes

logger = logging.getLogger(__name__)

_MAX_PROPS_BYTES = 2048
_MAX_PROPS_KEYS = 24
_MAX_STR = 120


def hash_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()


def client_config() -> dict[str, Any]:
    """Runtime config handed to the Android SDK (kill switch + sampling + batching)."""
    return {
        "enabled": settings.analytics_enabled,
        "schema_version": SCHEMA_VERSION,
        "min_schema_version": MIN_SUPPORTED_SCHEMA,
        "sample_rate": max(0.0, min(1.0, settings.analytics_sample_rate)),
        "event_sample_rates": PER_EVENT_SAMPLE,
        "batch_size": 20,
        "max_batch": settings.analytics_max_batch,
        "flush_interval_seconds": 30,
        "max_event_age_days": settings.analytics_max_event_age_days,
    }


def sanitize_props(props: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Keep only scalar props with safe keys; scrub PII-looking values. Returns (clean, dropped_count)."""
    clean: dict[str, Any] = {}
    dropped = 0
    for key, value in props.items():
        if len(clean) >= _MAX_PROPS_KEYS:
            dropped += 1
            continue
        if not isinstance(key, str) or not PROP_KEY_RE.match(key) or is_pii_key(key):
            dropped += 1
            continue
        if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
            clean[key] = value
        elif isinstance(value, str):
            clean[key] = scrub_value(value)[:_MAX_STR]
        else:
            dropped += 1
    return clean, dropped


def correct_time(
    occurred_at: datetime, *, sent_at: datetime | None, now: datetime
) -> tuple[datetime, int | None, str | None]:
    """Return (corrected_time, skew_ms, reject_reason).

    age = sent_at - occurred_at is measured on the device clock only, so
    corrected = server_now - age is immune to a wrong wall clock. Without sent_at fall back to the
    raw timestamp, clamped to [now - max_age, now + max_future].
    """
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    skew_ms: int | None = None
    if sent_at is not None:
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        skew_ms = int((now - sent_at).total_seconds() * 1000)
        age = sent_at - occurred_at
        corrected = now - age
    else:
        corrected = occurred_at
    if corrected < now - timedelta(days=settings.analytics_max_event_age_days):
        return corrected, skew_ms, "too_old"
    if corrected > now + timedelta(seconds=settings.analytics_max_future_seconds):
        corrected = now
    return corrected, skew_ms, None


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
        if body.schema_version < MIN_SUPPORTED_SCHEMA or body.schema_version > SCHEMA_VERSION:
            raise AppError(ErrorCodes.AUTH_INVALID, f"不支持的 schema_version={body.schema_version}", status_code=400)
        if len(body.events) > settings.analytics_max_batch:
            raise AppError(ErrorCodes.AUTH_INVALID, "单批事件过多", status_code=413)
        now = datetime.now(timezone.utc)
        ip_hash = hash_ip(client_ip)
        user_id: UUID | None = user.id if user is not None else None
        accepted = 0
        duplicated = 0
        rejected: list[dict] = []
        unknown = 0
        sanitized = 0
        seen_devices: dict[str, AnalyticsEventIn] = {}

        for event in body.events:
            reason = self._validate(event)
            if reason:
                rejected.append({"event_id": str(event.event_id), "reason": reason})
                continue
            if event.event_name not in EVENTS:
                unknown += 1
            props, dropped = sanitize_props(event.props)
            sanitized += dropped
            encoded = json.dumps(props, ensure_ascii=False, default=str)
            if len(encoded.encode("utf-8")) > _MAX_PROPS_BYTES:
                rejected.append({"event_id": str(event.event_id), "reason": "props_too_large"})
                continue
            occurred, skew_ms, bad = correct_time(event.occurred_at, sent_at=body.sent_at, now=now)
            if bad:
                rejected.append({"event_id": str(event.event_id), "reason": bad})
                continue

            inserted = await self.db.execute(
                text(
                    "INSERT INTO analytics_event_dedupe (event_id) VALUES (CAST(:event_id AS uuid)) "
                    "ON CONFLICT (event_id) DO NOTHING RETURNING event_id"
                ),
                {"event_id": str(event.event_id)},
            )
            if inserted.first() is None:
                duplicated += 1
                continue

            object_type = event_object_type(event.event_name, event.object_type)
            object_id = event.object_id if object_type else None
            client_ts = event.occurred_at if event.occurred_at.tzinfo else event.occurred_at.replace(tzinfo=timezone.utc)
            await self.db.execute(
                text(
                    """
                    INSERT INTO analytics_events (
                        event_id, event_name, user_id, anon_id, session_id,
                        screen, referrer_screen, props, platform, app_version,
                        build_type, os_version, device_model, network_type,
                        city, ip_hash, occurred_at,
                        schema_version, sdk_version, channel, experiments, object_type, object_id,
                        duration_ms, seq, client_ts, skew_ms
                    ) VALUES (
                        CAST(:event_id AS uuid), :event_name, :user_id, :anon_id, :session_id,
                        :screen, :referrer_screen, CAST(:props AS jsonb), :platform, :app_version,
                        :build_type, :os_version, :device_model, :network_type,
                        NULL, :ip_hash, :occurred_at,
                        :schema_version, :sdk_version, :channel, CAST(:experiments AS jsonb), :object_type, :object_id,
                        :duration_ms, :seq, :client_ts, :skew_ms
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
                    "occurred_at": occurred,
                    "schema_version": body.schema_version,
                    "sdk_version": body.sdk_version,
                    "channel": event.channel,
                    "experiments": json.dumps(event.experiments, ensure_ascii=False) if event.experiments else None,
                    "object_type": object_type,
                    "object_id": object_id,
                    "duration_ms": event.duration_ms,
                    "seq": event.seq,
                    "client_ts": client_ts,
                    "skew_ms": skew_ms,
                },
            )
            seen_devices[event.anon_id] = event
            accepted += 1

        for anon_id, ev in seen_devices.items():
            await self.db.execute(
                text(
                    """
                    INSERT INTO analytics_devices (anon_id, first_seen_at, last_seen_at, user_id, platform,
                                                   first_app_version, app_version, channel)
                    VALUES (:anon_id, now(), now(), :user_id, :platform, :app_version, :app_version, :channel)
                    ON CONFLICT (anon_id) DO UPDATE SET
                        last_seen_at = now(),
                        user_id = COALESCE(EXCLUDED.user_id, analytics_devices.user_id),
                        app_version = EXCLUDED.app_version,
                        channel = COALESCE(EXCLUDED.channel, analytics_devices.channel)
                    """
                ),
                {
                    "anon_id": anon_id,
                    "user_id": user_id,
                    "platform": ev.platform,
                    "app_version": ev.app_version,
                    "channel": ev.channel,
                },
            )
        await self.db.commit()
        if unknown:
            logger.info("analytics unknown events=%d", unknown)
        return {
            "accepted": accepted,
            "duplicated": duplicated,
            "rejected": rejected,
            "sanitized_props": sanitized,
            "server_time": now.isoformat(),
            "config": client_config(),
        }

    @staticmethod
    def _validate(event: AnalyticsEventIn) -> str | None:
        if not EVENT_NAME_RE.match(event.event_name):
            return "bad_event_name"
        if event.object_type is not None and event.object_id is None:
            return "object_id_required"
        return None

    async def delete_my_data(self, *, user_id: UUID | None, anon_id: str | None) -> dict:
        """Right-to-erasure / opt-out: remove raw events and the device row for this user/device."""
        deleted = 0
        if user_id is not None:
            r = await self.db.execute(text("DELETE FROM analytics_events WHERE user_id = :u"), {"u": user_id})
            deleted += r.rowcount or 0
            await self.db.execute(text("DELETE FROM analytics_devices WHERE user_id = :u"), {"u": user_id})
        if anon_id:
            r = await self.db.execute(text("DELETE FROM analytics_events WHERE anon_id = :a"), {"a": anon_id})
            deleted += r.rowcount or 0
            await self.db.execute(text("DELETE FROM analytics_devices WHERE anon_id = :a"), {"a": anon_id})
        await self.db.commit()
        return {"deleted": deleted}
