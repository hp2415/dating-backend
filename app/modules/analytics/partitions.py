"""Create upcoming analytics partitions and drop ones older than the retention window."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _add_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


async def ensure_future_partitions(db: AsyncSession, *, months_ahead: int = 3) -> list[str]:
    today = date.today()
    created: list[str] = []
    for offset in range(0, months_ahead):
        year, month = _add_month(today.year, today.month, offset)
        next_year, next_month = _add_month(year, month, 1)
        start = date(year, month, 1)
        end = date(next_year, next_month, 1)
        name = f"analytics_events_{year:04d}{month:02d}"
        await db.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS {name} PARTITION OF analytics_events
                FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')
                """
            )
        )
        created.append(name)
    return created


async def drop_expired_partitions(db: AsyncSession, *, keep_days: int = 90) -> list[str]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    rows = await db.execute(
        text(
            """
            SELECT c.relname
            FROM pg_inherits i
            JOIN pg_class c ON c.oid = i.inhrelid
            JOIN pg_class p ON p.oid = i.inhparent
            WHERE p.relname = 'analytics_events'
            """
        )
    )
    dropped: list[str] = []
    for (name,) in rows.all():
        suffix = name.removeprefix("analytics_events_")
        if len(suffix) != 6 or not suffix.isdigit():
            continue
        year = int(suffix[:4])
        month = int(suffix[4:])
        next_year, next_month = _add_month(year, month, 1)
        partition_end = datetime(next_year, next_month, 1, tzinfo=timezone.utc)
        if partition_end >= cutoff:
            continue
        await db.execute(text(f"DROP TABLE IF EXISTS {name}"))
        dropped.append(name)
    await db.execute(
        text(
            "DELETE FROM analytics_event_dedupe WHERE received_at < now() - make_interval(days => :days)"
        ),
        {"days": keep_days},
    )
    return dropped
