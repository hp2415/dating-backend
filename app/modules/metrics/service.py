"""Idempotent daily metrics. GMV and paid counts come from orders, not events."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

SHANGHAI = ZoneInfo("Asia/Shanghai")

FUNNEL_STEPS = (
    "app.launched",
    "auth.login_succeeded",
    "activity.detail_viewed",
    "activity.join_succeeded",
    "companion.booking_created",
    "commerce.pay_succeeded",
)


class MetricsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def rebuild_day(self, day: date) -> dict:
        start, end = _bounds(day)
        dau = await self._scalar(
            """
            SELECT COUNT(DISTINCT COALESCE(user_id::text, anon_id))
            FROM analytics_events
            WHERE received_at >= :start AND received_at < :end
            """,
            start,
            end,
        )
        new_users = await self._scalar(
            """
            SELECT COUNT(*) FROM users
            WHERE created_at >= :start AND created_at < :end
            """,
            start,
            end,
        )
        published = await self._scalar(
            """
            SELECT COUNT(*) FROM activities
            WHERE status = 'published'
              AND COALESCE(reviewed_at, created_at) >= :start
              AND COALESCE(reviewed_at, created_at) < :end
            """,
            start,
            end,
        )
        orders = await self.db.execute(
            text(
                """
                SELECT COUNT(*), COALESCE(SUM(payable_cents), 0)
                FROM orders
                WHERE status = 'paid'
                  AND paid_at >= :start AND paid_at < :end
                """
            ),
            {"start": start, "end": end},
        )
        orders_paid, gmv_cents = orders.one()
        funnel = await self._funnel(start, end)
        retention = await self._retention(day, start)
        await self.db.execute(
            text(
                """
                INSERT INTO metrics_daily (
                    day, dau, new_users, activities_published, orders_paid,
                    gmv_cents, funnel, retention, computed_at
                ) VALUES (
                    :day, :dau, :new_users, :published, :orders_paid,
                    :gmv, CAST(:funnel AS jsonb), CAST(:retention AS jsonb), now()
                )
                ON CONFLICT (day) DO UPDATE SET
                    dau = EXCLUDED.dau,
                    new_users = EXCLUDED.new_users,
                    activities_published = EXCLUDED.activities_published,
                    orders_paid = EXCLUDED.orders_paid,
                    gmv_cents = EXCLUDED.gmv_cents,
                    funnel = EXCLUDED.funnel,
                    retention = EXCLUDED.retention,
                    computed_at = EXCLUDED.computed_at
                """
            ),
            {
                "day": day,
                "dau": int(dau),
                "new_users": int(new_users),
                "published": int(published),
                "orders_paid": int(orders_paid or 0),
                "gmv": int(gmv_cents or 0),
                "funnel": _json(funnel),
                "retention": _json(retention),
            },
        )
        return {
            "day": day.isoformat(),
            "dau": int(dau),
            "new_users": int(new_users),
            "activities_published": int(published),
            "orders_paid": int(orders_paid or 0),
            "gmv_cents": int(gmv_cents or 0),
            "funnel": funnel,
            "retention": retention,
        }

    async def rebuild_recent(self, days: int) -> list[dict]:
        today = datetime.now(SHANGHAI).date()
        span = max(1, min(days, 90))
        rows = []
        for offset in range(span - 1, -1, -1):
            rows.append(await self.rebuild_day(today - timedelta(days=offset)))
        return rows

    async def overview(self, days: int) -> dict:
        span = max(1, min(days, 90))
        today = datetime.now(SHANGHAI).date()
        start = today - timedelta(days=span - 1)
        prev_start = start - timedelta(days=span)
        series = await self._range(start, today + timedelta(days=1))
        previous = await self._range(prev_start, start)
        totals = _sum_rows(series)
        prev_totals = _sum_rows(previous)
        return {
            "days": span,
            "from": start.isoformat(),
            "to": today.isoformat(),
            "series": series,
            "totals": totals,
            "previous": prev_totals,
            "change": {key: _ratio(totals[key], prev_totals[key]) for key in totals},
        }

    async def funnel(self, name: str, day_from: date, day_to: date) -> dict:
        start, _ = _bounds(day_from)
        _, end = _bounds(day_to)
        steps = await self._funnel(start, end)
        return {
            "name": name or "core",
            "from": day_from.isoformat(),
            "to": day_to.isoformat(),
            "steps": [{"event": event, "count": steps.get(event, 0)} for event in FUNNEL_STEPS],
        }

    async def retention(self, cohort: date) -> dict:
        row = await self.db.execute(
            text("SELECT retention FROM metrics_daily WHERE day = :day"),
            {"day": cohort},
        )
        found = row.first()
        if found is not None and found[0]:
            stored = found[0]
            return {"cohort": cohort.isoformat(), **stored}
        start, _ = _bounds(cohort)
        computed = await self._retention(cohort, start)
        return {"cohort": cohort.isoformat(), **computed}

    async def _range(self, start: date, end_exclusive: date) -> list[dict]:
        rows = await self.db.execute(
            text(
                """
                SELECT day, dau, new_users, activities_published, orders_paid, gmv_cents
                FROM metrics_daily
                WHERE day >= :start AND day < :end
                ORDER BY day
                """
            ),
            {"start": start, "end": end_exclusive},
        )
        return [
            {
                "day": item.day.isoformat(),
                "dau": int(item.dau),
                "new_users": int(item.new_users),
                "activities_published": int(item.activities_published),
                "orders_paid": int(item.orders_paid),
                "gmv_cents": int(item.gmv_cents),
            }
            for item in rows
        ]

    async def _funnel(self, start: datetime, end: datetime) -> dict:
        counts: dict[str, int] = {}
        for event in FUNNEL_STEPS:
            counts[event] = int(
                await self._scalar(
                    """
                    SELECT COUNT(DISTINCT COALESCE(user_id::text, anon_id))
                    FROM analytics_events
                    WHERE event_name = :name
                      AND received_at >= :start AND received_at < :end
                    """,
                    start,
                    end,
                    extra={"name": event},
                )
            )
        return counts

    async def _retention(self, cohort: date, cohort_start: datetime) -> dict:
        cohort_end = cohort_start + timedelta(days=1)
        size = int(
            await self._scalar(
                """
                SELECT COUNT(*) FROM users
                WHERE created_at >= :start AND created_at < :end
                """,
                cohort_start,
                cohort_end,
            )
        )
        now = datetime.now(timezone.utc)
        result: dict[str, float | int | None] = {"cohort_size": size}
        for label, offset in (("d1", 1), ("d7", 7), ("d30", 30)):
            window_start = cohort_start + timedelta(days=offset)
            window_end = window_start + timedelta(days=1)
            if window_end > now or size == 0:
                result[label] = None
                continue
            active = int(
                await self._scalar(
                    """
                    SELECT COUNT(DISTINCT e.user_id)
                    FROM analytics_events e
                    WHERE e.user_id IN (
                        SELECT id FROM users
                        WHERE created_at >= :cohort_start AND created_at < :cohort_end
                    )
                      AND e.received_at >= :start AND e.received_at < :end
                    """,
                    window_start,
                    window_end,
                    extra={"cohort_start": cohort_start, "cohort_end": cohort_end},
                )
            )
            result[label] = round(active / size, 4)
        return result

    async def _scalar(
        self,
        sql: str,
        start: datetime,
        end: datetime,
        extra: dict | None = None,
    ) -> int:
        params = {"start": start, "end": end}
        if extra:
            params.update(extra)
        value = await self.db.scalar(text(sql), params)
        return int(value or 0)


def _bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=SHANGHAI)
    return start, start + timedelta(days=1)


def _json(payload: dict) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False)


def _sum_rows(rows: list[dict]) -> dict:
    keys = ("dau", "new_users", "activities_published", "orders_paid", "gmv_cents")
    return {key: sum(int(row.get(key) or 0) for row in rows) for key in keys}


def _ratio(current: int, previous: int) -> float | None:
    if previous <= 0:
        return None
    return round((current - previous) / previous, 4)
