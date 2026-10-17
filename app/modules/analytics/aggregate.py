"""Nightly (and on-demand) aggregation of raw analytics_events into small, PII-free daily tables.

Day bucket = server receive time in Asia/Shanghai (late offline uploads land on the day they arrive;
``occurred_at`` is used only for ordering inside funnels and session length).
Every rebuild is idempotent: it deletes + rewrites the rows of that day.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics.taxonomy import (
    EVENTS,
    FEATURE_EVENTS,
    FUNNELS,
    STAGE_CLICK,
    STAGE_CONVERT,
    STAGE_DETAIL,
    STAGE_EXPOSURE,
    STAGE_PAY,
    FunnelStep,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")
logger = logging.getLogger(__name__)

ACTOR = "COALESCE(user_id::text, anon_id)"


def day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=SHANGHAI)
    return start, start + timedelta(days=1)


def _stage_events(stage: str) -> list[str]:
    return [n for n, d in EVENTS.items() if d.stage == stage]


def funnel_sql(steps: list[FunnelStep]) -> tuple[str, dict]:
    """Ordered funnel: each step counts actors whose first matching event is at/after their previous step."""
    params: dict = {}
    ctes: list[str] = []
    for i, step in enumerate(steps):
        params[f"e{i}"] = step.event
        cond = f"event_name = :e{i}"
        if step.object_type:
            params[f"o{i}"] = step.object_type
            cond += f" AND object_type = :o{i}"
        if i == 0:
            ctes.append(
                f"s0 AS (SELECT {ACTOR} AS actor, MIN(occurred_at) AS t FROM analytics_events "
                f"WHERE received_at >= :start AND received_at < :end AND {cond} GROUP BY 1)"
            )
        else:
            ctes.append(
                f"s{i} AS (SELECT e.actor, MIN(e.occurred_at) AS t FROM "
                f"(SELECT {ACTOR} AS actor, occurred_at FROM analytics_events "
                f"WHERE received_at >= :start AND received_at < :end AND {cond}) e "
                f"JOIN s{i-1} p ON p.actor = e.actor AND e.occurred_at >= p.t GROUP BY 1)"
            )
    union = " UNION ALL ".join(f"SELECT {i} AS idx, COUNT(*) AS n FROM s{i}" for i in range(len(steps)))
    return "WITH " + ", ".join(ctes) + " " + union + " ORDER BY idx", params


class AnalyticsAggregator:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def rebuild_day(self, day: date) -> dict:
        start, end = day_bounds(day)
        p = {"start": start, "end": end, "day": day}
        await self._events(p)
        await self._objects(p)
        await self._perf(p)
        funnels = await self._funnels(p)
        active = await self._active(day, start, end)
        return {"day": day.isoformat(), "funnels": funnels, **active}

    async def rebuild_recent(self, days: int) -> list[dict]:
        today = datetime.now(SHANGHAI).date()
        out = []
        for off in range(max(1, min(days, 90)) - 1, -1, -1):
            out.append(await self.rebuild_day(today - timedelta(days=off)))
        return out

    # ── feature usage / page stats ─────────────────────────
    async def _events(self, p: dict) -> None:
        await self.db.execute(text("DELETE FROM analytics_daily_event WHERE day = :day"), p)
        await self.db.execute(
            text(
                f"""
                INSERT INTO analytics_daily_event (day, event_name, screen, platform, events, users, sessions, avg_duration_ms)
                SELECT :day, event_name, COALESCE(screen, ''), platform, COUNT(*),
                       COUNT(DISTINCT {ACTOR}), COUNT(DISTINCT session_id),
                       AVG(duration_ms)::int
                FROM analytics_events
                WHERE received_at >= :start AND received_at < :end
                GROUP BY event_name, COALESCE(screen, ''), platform
                """
            ),
            p,
        )

    # ── per-object exposure → conversion ───────────────────
    async def _objects(self, p: dict) -> None:
        await self.db.execute(text("DELETE FROM analytics_daily_object WHERE day = :day"), p)
        params = {
            **p,
            "exposure": _stage_events(STAGE_EXPOSURE),
            "click": _stage_events(STAGE_CLICK),
            "detail": _stage_events(STAGE_DETAIL),
            "convert": _stage_events(STAGE_CONVERT),
            "pay": _stage_events(STAGE_PAY),
        }
        await self.db.execute(
            text(
                f"""
                INSERT INTO analytics_daily_object
                    (day, object_type, object_id, exposures, exposed_users, clicks, details, conversions, paid)
                SELECT :day, object_type, object_id,
                    COUNT(*) FILTER (WHERE event_name = ANY(:exposure)),
                    COUNT(DISTINCT {ACTOR}) FILTER (WHERE event_name = ANY(:exposure)),
                    COUNT(*) FILTER (WHERE event_name = ANY(:click)),
                    COUNT(*) FILTER (WHERE event_name = ANY(:detail)),
                    COUNT(*) FILTER (WHERE event_name = ANY(:convert)),
                    COUNT(*) FILTER (WHERE event_name = ANY(:pay))
                FROM analytics_events
                WHERE received_at >= :start AND received_at < :end AND object_id IS NOT NULL AND object_type IS NOT NULL
                GROUP BY object_type, object_id
                """
            ),
            params,
        )

    # ── performance percentiles ────────────────────────────
    async def _perf(self, p: dict) -> None:
        await self.db.execute(text("DELETE FROM analytics_daily_perf WHERE day = :day"), p)
        await self.db.execute(
            text(
                """
                INSERT INTO analytics_daily_perf (day, metric, app_version, n, avg_ms, p50_ms, p90_ms, p99_ms)
                SELECT :day,
                       CASE WHEN event_name = 'perf.api_latency' THEN 'api:' || COALESCE(props->>'path', '?')
                            WHEN event_name = 'perf.screen_rendered' THEN 'render:' || COALESCE(props->>'screen', screen, '?')
                            ELSE event_name END AS metric,
                       COALESCE(app_version, ''),
                       COUNT(*),
                       AVG(duration_ms)::int,
                       (percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_ms))::int,
                       (percentile_cont(0.9) WITHIN GROUP (ORDER BY duration_ms))::int,
                       (percentile_cont(0.99) WITHIN GROUP (ORDER BY duration_ms))::int
                FROM analytics_events
                WHERE received_at >= :start AND received_at < :end
                  AND event_name IN ('perf.cold_start', 'perf.screen_rendered', 'perf.api_latency')
                  AND duration_ms IS NOT NULL
                GROUP BY 2, 3
                """
            ),
            p,
        )
        # Jank % = slow_frames / frames, weighted over the day (not an average of averages).
        await self.db.execute(
            text(
                """
                INSERT INTO analytics_daily_perf (day, metric, app_version, n, avg_ms, p50_ms, p90_ms, p99_ms)
                SELECT :day, 'jank_pct_x100', COALESCE(app_version, ''), COUNT(*),
                       CASE WHEN SUM((props->>'frames')::numeric) > 0
                            THEN (SUM((props->>'slow_frames')::numeric) * 10000 / SUM((props->>'frames')::numeric))::int END,
                       NULL, NULL, NULL
                FROM analytics_events
                WHERE received_at >= :start AND received_at < :end AND event_name = 'perf.frame_stats'
                  AND (props->>'frames') ~ '^[0-9]+$' AND (props->>'slow_frames') ~ '^[0-9]+$'
                GROUP BY 3
                """
            ),
            p,
        )

    # ── funnels ────────────────────────────────────────────
    async def _funnels(self, p: dict) -> int:
        await self.db.execute(text("DELETE FROM analytics_daily_funnel WHERE day = :day"), p)
        for key, (_, steps) in FUNNELS.items():
            sql, params = funnel_sql(steps)
            rows = (await self.db.execute(text(sql), {**params, "start": p["start"], "end": p["end"]})).all()
            counts = {int(r.idx): int(r.n) for r in rows}
            for i, step in enumerate(steps):
                await self.db.execute(
                    text(
                        "INSERT INTO analytics_daily_funnel (day, funnel, step_index, event_name, users) "
                        "VALUES (:day, :f, :i, :e, :u)"
                    ),
                    {"day": p["day"], "f": key, "i": i, "e": step.event, "u": counts.get(i, 0)},
                )
        return len(FUNNELS)

    # ── DAU / WAU / MAU / sessions / new devices / device retention ──
    async def _active(self, day: date, start: datetime, end: datetime) -> dict:
        async def scalar(sql: str, **params) -> int:
            return int((await self.db.scalar(text(sql), params)) or 0)

        dau = await scalar(
            f"SELECT COUNT(DISTINCT {ACTOR}) FROM analytics_events WHERE received_at >= :s AND received_at < :e",
            s=start, e=end,
        )
        wau = await scalar(
            f"SELECT COUNT(DISTINCT {ACTOR}) FROM analytics_events WHERE received_at >= :s AND received_at < :e",
            s=end - timedelta(days=7), e=end,
        )
        mau = await scalar(
            f"SELECT COUNT(DISTINCT {ACTOR}) FROM analytics_events WHERE received_at >= :s AND received_at < :e",
            s=end - timedelta(days=30), e=end,
        )
        sess = (
            await self.db.execute(
                text(
                    """
                    SELECT COUNT(*), COALESCE(AVG(len), 0)::int FROM (
                        SELECT session_id, EXTRACT(EPOCH FROM (MAX(occurred_at) - MIN(occurred_at))) AS len
                        FROM analytics_events WHERE received_at >= :s AND received_at < :e GROUP BY session_id
                    ) x
                    """
                ),
                {"s": start, "e": end},
            )
        ).one()
        new_devices = await scalar(
            "SELECT COUNT(*) FROM analytics_devices WHERE first_seen_at >= :s AND first_seen_at < :e", s=start, e=end
        )
        retention = await self._device_retention(start)
        import json

        await self.db.execute(
            text(
                """
                INSERT INTO metrics_daily (day, dau, wau, mau, sessions, avg_session_seconds, new_devices, device_retention, computed_at)
                VALUES (:day, :dau, :wau, :mau, :sessions, :avg, :nd, CAST(:ret AS jsonb), now())
                ON CONFLICT (day) DO UPDATE SET dau = EXCLUDED.dau, wau = EXCLUDED.wau, mau = EXCLUDED.mau,
                    sessions = EXCLUDED.sessions, avg_session_seconds = EXCLUDED.avg_session_seconds,
                    new_devices = EXCLUDED.new_devices, device_retention = EXCLUDED.device_retention,
                    computed_at = EXCLUDED.computed_at
                """
            ),
            {"day": day, "dau": dau, "wau": wau, "mau": mau, "sessions": int(sess[0]), "avg": int(sess[1]),
             "nd": new_devices, "ret": json.dumps(retention)},
        )
        return {"dau": dau, "wau": wau, "mau": mau, "sessions": int(sess[0]), "new_devices": new_devices}

    async def _device_retention(self, cohort_start: datetime) -> dict:
        """Install-cohort retention: share of devices first seen on `cohort` active again on day N."""
        cohort_end = cohort_start + timedelta(days=1)
        size = int(
            (await self.db.scalar(
                text("SELECT COUNT(*) FROM analytics_devices WHERE first_seen_at >= :s AND first_seen_at < :e"),
                {"s": cohort_start, "e": cohort_end},
            )) or 0
        )
        out: dict = {"cohort_size": size}
        now = datetime.now(SHANGHAI)
        for label, off in (("d1", 1), ("d3", 3), ("d7", 7), ("d14", 14), ("d30", 30)):
            ws = cohort_start + timedelta(days=off)
            we = ws + timedelta(days=1)
            if size == 0 or we > now:
                out[label] = None
                continue
            n = int(
                (await self.db.scalar(
                    text(
                        """
                        SELECT COUNT(DISTINCT e.anon_id) FROM analytics_events e
                        WHERE e.received_at >= :ws AND e.received_at < :we
                          AND e.anon_id IN (SELECT anon_id FROM analytics_devices
                                            WHERE first_seen_at >= :cs AND first_seen_at < :ce)
                        """
                    ),
                    {"ws": ws, "we": we, "cs": cohort_start, "ce": cohort_end},
                )) or 0
            )
            out[label] = round(n / size, 4)
        return out

    # ── live (non-stored) ordered funnel over a range ──────
    async def live_funnel(self, key: str, day_from: date, day_to: date, *, platform: str | None = None) -> dict:
        label, steps = FUNNELS[key]
        start, _ = day_bounds(day_from)
        _, end = day_bounds(day_to)
        sql, params = funnel_sql(steps)
        if platform:
            sql = sql.replace("WHERE received_at >= :start", "WHERE platform = :platform AND received_at >= :start")
            params["platform"] = platform
        rows = (await self.db.execute(text(sql), {**params, "start": start, "end": end})).all()
        counts = {int(r.idx): int(r.n) for r in rows}
        first = counts.get(0, 0)
        out = []
        prev = None
        for i, st in enumerate(steps):
            n = counts.get(i, 0)
            out.append({
                "index": i, "event": st.event, "object_type": st.object_type, "users": n,
                "rate_from_prev": round(n / prev, 4) if prev else None,
                "rate_from_first": round(n / first, 4) if first else None,
            })
            prev = n
        return {"funnel": key, "label": label, "from": day_from.isoformat(), "to": day_to.isoformat(), "steps": out}
