"""ARQ worker settings — queues: default / notify / moderation / stats."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from arq import cron
from arq.connections import RedisSettings

from app.shared.config import settings
from app.shared.observability import configure_logging, init_sentry
from workers.tasks import (
    drain_domain_events,
    expire_unpaid_orders,
    finance_reconciliation_stub,
    heartbeat,
    maintain_analytics_partitions,
    materialize_dashboard_stub,
    remind_upcoming_activities_stub,
)

logger = logging.getLogger("dating-worker")


def _redis_settings() -> RedisSettings:
    parsed = urlparse(settings.redis_url)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=int((parsed.path or "/0").lstrip("/") or "0"),
        password=parsed.password,
    )


async def startup(ctx: dict) -> None:
    configure_logging()
    init_sentry()
    from app.shared.db import SessionLocal, engine

    ctx["db_factory"] = SessionLocal
    ctx["engine"] = engine
    redis = _redis_settings()
    logger.info(
        "ARQ worker started env=%s redis=%s:%s/%s",
        settings.app_env,
        redis.host,
        redis.port,
        redis.database,
    )


async def shutdown(ctx: dict) -> None:
    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()
    logger.info("ARQ worker stopped")


class WorkerSettings:
    functions = [
        drain_domain_events,
        heartbeat,
        maintain_analytics_partitions,
        expire_unpaid_orders,
        remind_upcoming_activities_stub,
        materialize_dashboard_stub,
        finance_reconciliation_stub,
    ]
    cron_jobs = [
        cron(heartbeat, second={0, 10, 20, 30, 40, 50}),
        cron(drain_domain_events, second={0, 15, 30, 45}),
        cron(expire_unpaid_orders, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
        cron(remind_upcoming_activities_stub, minute={0, 30}),
        cron(maintain_analytics_partitions, hour={2}, minute={10}),
        cron(materialize_dashboard_stub, hour={1}, minute={5}),
        cron(finance_reconciliation_stub, hour={3}, minute={10}),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = _redis_settings()
    max_jobs = 10
    job_timeout = 120
