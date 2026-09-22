"""ARQ job implementations."""

from __future__ import annotations

import logging
from typing import Any

from redis.asyncio import Redis

from app.modules.events.dispatch import dispatch_event
from app.modules.events.service import DomainEventService
from app.shared.config import settings

logger = logging.getLogger("dating-worker.tasks")


async def heartbeat(ctx: dict[str, Any]) -> str:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await redis.set("worker:heartbeat", "1", ex=30)
        await redis.set("worker:arq", "1", ex=30)
    finally:
        await redis.aclose()
    return "ok"


async def drain_domain_events(ctx: dict[str, Any]) -> dict[str, int]:
    factory = ctx["db_factory"]
    done = 0
    failed = 0
    async with factory() as session:
        service = DomainEventService(session)
        events = await service.claim_batch()
        for event in events:
            try:
                await dispatch_event(event)
                await service.mark_done(event)
                done += 1
            except Exception as exc:  # noqa: BLE001
                logger.exception("domain_event failed id=%s name=%s", event.id, event.name)
                await service.mark_failed(event, str(exc), retry=True)
                failed += 1
        await session.commit()
    if done or failed:
        logger.info("drain_domain_events done=%s failed=%s", done, failed)
    return {"done": done, "failed": failed}


async def expire_unpaid_orders(ctx: dict[str, Any]) -> dict[str, int]:
    factory = ctx["db_factory"]
    async with factory() as session:
        from app.modules.commerce.service import CommerceService

        n = await CommerceService(session).expire_unpaid_orders(limit=200)
        await session.commit()
    if n:
        logger.info("expire_unpaid_orders count=%s", n)
    return {"expired": n}


async def remind_upcoming_activities_stub(ctx: dict[str, Any]) -> str:
    """M5+: schedule push for activities starting within 1h."""
    logger.debug("remind_upcoming_activities_stub tick")
    return "stub"


async def maintain_analytics_partitions(ctx: dict[str, Any]) -> dict[str, list[str]]:
    factory = ctx["db_factory"]
    async with factory() as session:
        from app.modules.analytics.partitions import drop_expired_partitions, ensure_future_partitions

        created = await ensure_future_partitions(session, months_ahead=3)
        dropped = await drop_expired_partitions(session, keep_days=90)
        await session.commit()
    if dropped:
        logger.info("analytics partitions dropped=%s", dropped)
    return {"ensured": created, "dropped": dropped}


async def materialize_dashboard_stub(ctx: dict[str, Any]) -> str:
    """Nightly product metrics for yesterday (Asia/Shanghai). Name kept for the cron job."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    from app.modules.metrics.service import MetricsService
    from app.shared.db import SessionLocal

    day = (datetime.now(ZoneInfo("Asia/Shanghai")) - timedelta(days=1)).date()
    async with SessionLocal() as session:
        await MetricsService(session).rebuild_day(day)
        await session.commit()
    logger.info("metrics_daily rebuilt day=%s", day.isoformat())
    return day.isoformat()


async def finance_reconciliation_stub(ctx: dict[str, Any]) -> str:
    """M4 stub — real channel bill match after payment SDK."""
    logger.debug("finance_reconciliation_stub tick")
    return "stub"
