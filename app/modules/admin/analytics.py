"""Admin: analytics dashboards, event lookup and export.

Permission model (see ROLE_PERMISSIONS):
  analytics:read     aggregated dashboards (no user-level data)
  analytics:events   raw event lookup — identifiers are pseudonymised unless analytics:pii
  analytics:pii      plaintext user_id / anon_id, and lookup by user_id (customer-service troubleshooting)
  analytics:export   CSV export (needs a written reason, row-capped, always audited)
  analytics:rebuild  re-run aggregation
Every raw lookup and every export writes an admin audit-log row (who, filters, row count, masked?).
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminUser
from app.modules.admin.audit import write_audit
from app.modules.admin.deps import require_perm
from app.modules.admin.service import has_permission
from app.modules.analytics.aggregate import SHANGHAI, AnalyticsAggregator, day_bounds
from app.modules.analytics.taxonomy import EVENTS, FUNNELS, OBJECT_TYPES
from app.shared.config import settings
from app.shared.deps import get_db, get_request_id
from app.shared.errors import AppError
from app.shared.response import ErrorCodes, ok

router = APIRouter(prefix="/admin/v1/analytics", tags=["admin-analytics"])


# ── masking ────────────────────────────────────────────────
def pseudonym(value: str | None, prefix: str = "u") -> str | None:
    if not value:
        return None
    digest = hmac.new(settings.admin_jwt_secret.encode(), str(value).encode(), hashlib.sha256).hexdigest()
    return f"{prefix}_{digest[:10]}"


def mask_event_row(row: dict[str, Any], *, unmasked: bool) -> dict[str, Any]:
    if unmasked:
        return row
    out = dict(row)
    out["user_id"] = pseudonym(row.get("user_id"), "u")
    out["anon_id"] = pseudonym(row.get("anon_id"), "d")
    out.pop("ip_hash", None)
    return out


def _days(value_from: date | None, value_to: date | None, *, default_days: int, max_days: int | None = None) -> tuple[date, date]:
    today = datetime.now(SHANGHAI).date()
    end = value_to or today
    start = value_from or (end - timedelta(days=default_days - 1))
    if end < start:
        start, end = end, start
    limit = max_days if max_days is not None else settings.analytics_query_max_days
    if (end - start).days + 1 > limit:
        raise AppError(ErrorCodes.AUTH_INVALID, f"查询范围最多 {limit} 天", status_code=400)
    return start, end


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# ── overview ───────────────────────────────────────────────
@router.get("/overview")
async def overview(
    request: Request,
    days: int = Query(default=14, ge=1, le=90),
    admin: AdminUser = Depends(require_perm("analytics:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    today = datetime.now(SHANGHAI).date()
    start = today - timedelta(days=days - 1)
    rows = (
        await db.execute(
            text(
                """
                SELECT day, dau, wau, mau, sessions, avg_session_seconds, new_devices, device_retention
                FROM metrics_daily WHERE day >= :s AND day <= :e ORDER BY day
                """
            ),
            {"s": start, "e": today},
        )
    ).all()
    series = [
        {
            "day": r.day.isoformat(), "dau": r.dau, "wau": r.wau, "mau": r.mau, "sessions": r.sessions,
            "avg_session_seconds": r.avg_session_seconds, "new_devices": r.new_devices,
            "retention": r.device_retention or {},
        }
        for r in rows
    ]
    latest = series[-1] if series else None
    stickiness = round(latest["dau"] / latest["mau"], 4) if latest and latest["mau"] else None
    return ok(
        {"days": days, "series": series, "latest": latest, "stickiness": stickiness},
        request_id=get_request_id(request),
    )


@router.post("/rebuild")
async def rebuild(
    request: Request,
    days: int = Query(default=2, ge=1, le=14),
    admin: AdminUser = Depends(require_perm("analytics:rebuild")),
    db: AsyncSession = Depends(get_db),
):
    rows = await AnalyticsAggregator(db).rebuild_recent(days)
    write_audit(db, admin, action="analytics_rebuild", target_type="analytics", detail={"days": days}, ip=_ip(request))
    await db.commit()
    return ok({"rebuilt": len(rows), "days": rows}, request_id=get_request_id(request))


# ── catalog / funnels ──────────────────────────────────────
@router.get("/catalog")
async def catalog(request: Request, admin: AdminUser = Depends(require_perm("analytics:read"))):
    _ = admin
    items = [
        {"name": d.name, "category": d.category, "desc": d.desc, "props": d.props, "stage": d.stage, "object_type": d.object_type}
        for d in EVENTS.values()
    ]
    funnels = [
        {"key": k, "label": label, "steps": [{"event": s.event, "object_type": s.object_type} for s in steps]}
        for k, (label, steps) in FUNNELS.items()
    ]
    return ok({"events": items, "funnels": funnels, "object_types": list(OBJECT_TYPES)}, request_id=get_request_id(request))


@router.get("/funnel")
async def funnel(
    request: Request,
    name: str = Query(default="core"),
    day_from: date | None = Query(default=None, alias="from"),
    day_to: date | None = Query(default=None, alias="to"),
    platform: str | None = Query(default=None, max_length=16),
    admin: AdminUser = Depends(require_perm("analytics:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    if name not in FUNNELS:
        raise AppError(ErrorCodes.AUTH_INVALID, "未知漏斗", status_code=404)
    start, end = _days(day_from, day_to, default_days=7)
    data = await AnalyticsAggregator(db).live_funnel(name, start, end, platform=platform)
    return ok(data, request_id=get_request_id(request))


# ── feature usage / pages ──────────────────────────────────
@router.get("/usage")
async def usage(
    request: Request,
    day_from: date | None = Query(default=None, alias="from"),
    day_to: date | None = Query(default=None, alias="to"),
    category: str | None = Query(default=None),
    admin: AdminUser = Depends(require_perm("analytics:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    start, end = _days(day_from, day_to, default_days=7, max_days=90)
    rows = (
        await db.execute(
            text(
                """
                SELECT event_name, SUM(events)::bigint AS events, ROUND(AVG(users))::int AS avg_daily_users,
                       MAX(users) AS peak_daily_users, SUM(sessions)::bigint AS sessions
                FROM (SELECT day, event_name, SUM(events) events, SUM(users) users, SUM(sessions) sessions
                      FROM analytics_daily_event WHERE day >= :s AND day <= :e GROUP BY day, event_name) t
                GROUP BY event_name ORDER BY events DESC
                """
            ),
            {"s": start, "e": end},
        )
    ).all()
    items = []
    for r in rows:
        d = EVENTS.get(r.event_name)
        if category and (not d or d.category != category):
            continue
        items.append(
            {
                "event": r.event_name, "category": d.category if d else "unknown", "desc": d.desc if d else "",
                "events": int(r.events), "avg_daily_users": int(r.avg_daily_users or 0),
                "peak_daily_users": int(r.peak_daily_users or 0), "sessions": int(r.sessions),
            }
        )
    return ok({"from": start.isoformat(), "to": end.isoformat(), "items": items}, request_id=get_request_id(request))


@router.get("/pages")
async def pages(
    request: Request,
    day_from: date | None = Query(default=None, alias="from"),
    day_to: date | None = Query(default=None, alias="to"),
    admin: AdminUser = Depends(require_perm("analytics:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    start, end = _days(day_from, day_to, default_days=7, max_days=90)
    rows = (
        await db.execute(
            text(
                """
                SELECT screen,
                       SUM(events) FILTER (WHERE event_name = 'page.viewed')::bigint AS views,
                       ROUND(AVG(users) FILTER (WHERE event_name = 'page.viewed'))::int AS avg_daily_users,
                       (SUM(avg_duration_ms::bigint * events) FILTER (WHERE event_name = 'page.left')
                          / NULLIF(SUM(events) FILTER (WHERE event_name = 'page.left'), 0))::int AS avg_dwell_ms
                FROM analytics_daily_event
                WHERE day >= :s AND day <= :e AND screen <> '' AND event_name IN ('page.viewed', 'page.left')
                GROUP BY screen ORDER BY views DESC NULLS LAST
                """
            ),
            {"s": start, "e": end},
        )
    ).all()
    items = [
        {"screen": r.screen, "views": int(r.views or 0), "avg_daily_users": int(r.avg_daily_users or 0), "avg_dwell_ms": r.avg_dwell_ms}
        for r in rows
    ]
    return ok({"from": start.isoformat(), "to": end.isoformat(), "items": items}, request_id=get_request_id(request))


# ── per-object exposure / conversion ───────────────────────
async def _titles(db: AsyncSession, object_type: str, ids: list[str]) -> dict[str, str]:
    if not ids:
        return {}
    uuids = []
    for i in ids:
        try:
            uuids.append(UUID(i))
        except ValueError:
            continue
    if not uuids:
        return {}
    sql = {
        "activity": "SELECT id::text, title FROM activities WHERE id = ANY(:ids)",
        "club": "SELECT id::text, name FROM clubs WHERE id = ANY(:ids)",
        "guild": "SELECT id::text, name FROM guilds WHERE id = ANY(:ids)",
        "post": "SELECT id::text, left(content, 30) FROM community_posts WHERE id = ANY(:ids)",
        "companion": "SELECT user_id::text, COALESCE(specialty, '') FROM companion_profiles WHERE user_id = ANY(:ids)",
    }.get(object_type)
    if not sql:
        return {}
    rows = (await db.execute(text(sql), {"ids": uuids})).all()
    return {r[0]: r[1] for r in rows}


@router.get("/objects")
async def objects(
    request: Request,
    object_type: str = Query(default="activity"),
    day_from: date | None = Query(default=None, alias="from"),
    day_to: date | None = Query(default=None, alias="to"),
    order: str = Query(default="exposures", pattern="^(exposures|clicks|details|conversions|paid)$"),
    limit: int = Query(default=30, ge=1, le=100),
    admin: AdminUser = Depends(require_perm("analytics:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    if object_type not in OBJECT_TYPES:
        raise AppError(ErrorCodes.AUTH_INVALID, "未知对象类型", status_code=400)
    start, end = _days(day_from, day_to, default_days=7, max_days=90)
    rows = (
        await db.execute(
            text(
                f"""
                SELECT object_id, SUM(exposures) exposures, SUM(exposed_users) exposed_users, SUM(clicks) clicks,
                       SUM(details) details, SUM(conversions) conversions, SUM(paid) paid
                FROM analytics_daily_object
                WHERE object_type = :t AND day >= :s AND day <= :e
                GROUP BY object_id ORDER BY {order} DESC, object_id LIMIT :n
                """
            ),
            {"t": object_type, "s": start, "e": end, "n": limit},
        )
    ).all()
    titles = await _titles(db, object_type, [r.object_id for r in rows])
    items = []
    for r in rows:
        exp, clk, det, conv = int(r.exposures), int(r.clicks), int(r.details), int(r.conversions)
        items.append(
            {
                "object_id": r.object_id, "title": titles.get(r.object_id),
                "exposures": exp, "exposed_users": int(r.exposed_users), "clicks": clk, "details": det,
                "conversions": conv, "paid": int(r.paid),
                "ctr": round(clk / exp, 4) if exp else None,
                "conversion_rate": round(conv / det, 4) if det else (round(conv / clk, 4) if clk else None),
            }
        )
    totals = {k: sum(i[k] for i in items) for k in ("exposures", "clicks", "details", "conversions", "paid")}
    return ok(
        {"object_type": object_type, "from": start.isoformat(), "to": end.isoformat(), "items": items, "totals": totals},
        request_id=get_request_id(request),
    )


# ── performance & errors ───────────────────────────────────
@router.get("/perf")
async def perf(
    request: Request,
    day_from: date | None = Query(default=None, alias="from"),
    day_to: date | None = Query(default=None, alias="to"),
    admin: AdminUser = Depends(require_perm("analytics:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    start, end = _days(day_from, day_to, default_days=7, max_days=90)
    rows = (
        await db.execute(
            text(
                """
                SELECT metric, app_version, SUM(n)::int n,
                       (SUM(avg_ms::bigint * n) / NULLIF(SUM(n), 0))::int avg_ms,
                       MAX(p50_ms) p50_ms, MAX(p90_ms) p90_ms, MAX(p99_ms) p99_ms
                FROM analytics_daily_perf WHERE day >= :s AND day <= :e AND metric <> 'jank_pct_x100'
                GROUP BY metric, app_version ORDER BY metric, app_version DESC
                """
            ),
            {"s": start, "e": end},
        )
    ).all()
    jank = (
        await db.execute(
            text(
                """
                SELECT day, app_version, avg_ms FROM analytics_daily_perf
                WHERE day >= :s AND day <= :e AND metric = 'jank_pct_x100' ORDER BY day
                """
            ),
            {"s": start, "e": end},
        )
    ).all()
    return ok(
        {
            "from": start.isoformat(), "to": end.isoformat(),
            "items": [dict(metric=r.metric, app_version=r.app_version, n=r.n, avg_ms=r.avg_ms, p50_ms=r.p50_ms, p90_ms=r.p90_ms, p99_ms=r.p99_ms) for r in rows],
            "jank": [{"day": r.day.isoformat(), "app_version": r.app_version, "jank_pct": (r.avg_ms or 0) / 100} for r in jank],
        },
        request_id=get_request_id(request),
    )


@router.get("/errors")
async def errors(
    request: Request,
    day_from: date | None = Query(default=None, alias="from"),
    day_to: date | None = Query(default=None, alias="to"),
    admin: AdminUser = Depends(require_perm("analytics:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    start, end = _days(day_from, day_to, default_days=3, max_days=14)
    s, _e = day_bounds(start)
    _s, e = day_bounds(end)
    rows = (
        await db.execute(
            text(
                """
                SELECT event_name,
                       COALESCE(props->>'path', props->>'exception', props->>'where', '?') AS k,
                       COALESCE(app_version, '') AS app_version,
                       COUNT(*) AS n, COUNT(DISTINCT anon_id) AS devices
                FROM analytics_events
                WHERE received_at >= :s AND received_at < :e AND event_name LIKE 'error.%'
                GROUP BY 1, 2, 3 ORDER BY n DESC LIMIT 100
                """
            ),
            {"s": s, "e": e},
        )
    ).all()
    return ok(
        {"from": start.isoformat(), "to": end.isoformat(),
         "items": [{"event": r.event_name, "key": r.k, "app_version": r.app_version, "count": int(r.n), "devices": int(r.devices)} for r in rows]},
        request_id=get_request_id(request),
    )


# ── raw event lookup + export (sensitive) ──────────────────
_EVENT_COLS = (
    "id, event_id::text AS event_id, event_name, user_id::text AS user_id, anon_id, session_id, screen, referrer_screen, "
    "props, platform, app_version, channel, os_version, device_model, network_type, object_type, object_id, "
    "duration_ms, experiments, schema_version, ip_hash, occurred_at, received_at, skew_ms"
)


def _event_filters(
    *, user_id: UUID | None, anon_id: str | None, session_id: str | None, event_name: str | None,
    screen: str | None, start: datetime, end: datetime, object_id: str | None,
) -> tuple[str, dict]:
    where = ["received_at >= :s", "received_at < :e"]
    params: dict[str, Any] = {"s": start, "e": end}
    if user_id:
        where.append("user_id = :user_id"); params["user_id"] = user_id
    if anon_id:
        where.append("anon_id = :anon_id"); params["anon_id"] = anon_id
    if session_id:
        where.append("session_id = :session_id"); params["session_id"] = session_id
    if event_name:
        where.append("event_name = :event_name"); params["event_name"] = event_name
    if screen:
        where.append("screen = :screen"); params["screen"] = screen
    if object_id:
        where.append("object_id = :object_id"); params["object_id"] = object_id
    return " AND ".join(where), params


def _row_to_dict(r) -> dict[str, Any]:
    d = dict(r._mapping)
    for k in ("occurred_at", "received_at"):
        if d.get(k) is not None:
            d[k] = d[k].isoformat()
    d["id"] = int(d["id"])
    return d


def _require_scope(admin: AdminUser, user_id: UUID | None, anon_id: str | None, session_id: str | None,
                   event_name: str | None, object_id: str | None) -> bool:
    """Returns True when the caller sees unmasked identifiers."""
    unmasked = has_permission(admin.role, "analytics:pii")
    if user_id is not None and not unmasked:
        raise AppError(ErrorCodes.ADMIN_FORBIDDEN, "按用户 ID 查询需要 analytics:pii 权限", status_code=403)
    if not any((user_id, anon_id, session_id, event_name, object_id)):
        raise AppError(ErrorCodes.AUTH_INVALID, "至少提供一个筛选条件（用户 / 设备 / 会话 / 事件 / 对象）", status_code=400)
    return unmasked


@router.get("/events")
async def events_lookup(
    request: Request,
    user_id: UUID | None = Query(default=None),
    anon_id: str | None = Query(default=None, max_length=64),
    session_id: str | None = Query(default=None, max_length=64),
    event_name: str | None = Query(default=None, max_length=64),
    screen: str | None = Query(default=None, max_length=64),
    object_id: str | None = Query(default=None, max_length=64),
    day_from: date | None = Query(default=None, alias="from"),
    day_to: date | None = Query(default=None, alias="to"),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("analytics:events")),
    db: AsyncSession = Depends(get_db),
):
    unmasked = _require_scope(admin, user_id, anon_id, session_id, event_name, object_id)
    start_d, end_d = _days(day_from, day_to, default_days=1)
    s, _e = day_bounds(start_d)
    _s, e = day_bounds(end_d)
    where, params = _event_filters(user_id=user_id, anon_id=anon_id, session_id=session_id, event_name=event_name,
                                   screen=screen, start=s, end=e, object_id=object_id)
    rows = (
        await db.execute(
            text(f"SELECT {_EVENT_COLS} FROM analytics_events WHERE {where} ORDER BY received_at DESC, id DESC LIMIT :n OFFSET :o"),
            {**params, "n": limit, "o": offset},
        )
    ).all()
    items = [mask_event_row(_row_to_dict(r), unmasked=unmasked) for r in rows]
    write_audit(
        db, admin, action="analytics_event_lookup", target_type="analytics_events",
        target_id=str(user_id) if user_id else (anon_id or session_id or event_name or object_id),
        detail={"filters": {"user_id": str(user_id) if user_id else None, "anon_id": anon_id, "session_id": session_id,
                            "event_name": event_name, "screen": screen, "object_id": object_id,
                            "from": start_d.isoformat(), "to": end_d.isoformat()},
                "rows": len(items), "unmasked": unmasked},
        ip=_ip(request),
    )
    await db.commit()
    return ok({"items": items, "limit": limit, "offset": offset, "masked": not unmasked}, request_id=get_request_id(request))


@router.get("/events/export")
async def events_export(
    request: Request,
    reason: str = Query(min_length=5, max_length=200),
    user_id: UUID | None = Query(default=None),
    anon_id: str | None = Query(default=None, max_length=64),
    session_id: str | None = Query(default=None, max_length=64),
    event_name: str | None = Query(default=None, max_length=64),
    screen: str | None = Query(default=None, max_length=64),
    object_id: str | None = Query(default=None, max_length=64),
    day_from: date | None = Query(default=None, alias="from"),
    day_to: date | None = Query(default=None, alias="to"),
    admin: AdminUser = Depends(require_perm("analytics:export")),
    db: AsyncSession = Depends(get_db),
):
    unmasked = _require_scope(admin, user_id, anon_id, session_id, event_name, object_id)
    start_d, end_d = _days(day_from, day_to, default_days=1)
    s, _e = day_bounds(start_d)
    _s, e = day_bounds(end_d)
    where, params = _event_filters(user_id=user_id, anon_id=anon_id, session_id=session_id, event_name=event_name,
                                   screen=screen, start=s, end=e, object_id=object_id)
    cap = settings.analytics_export_max_rows
    rows = (
        await db.execute(
            text(f"SELECT {_EVENT_COLS} FROM analytics_events WHERE {where} ORDER BY received_at, id LIMIT :n"),
            {**params, "n": cap + 1},
        )
    ).all()
    truncated = len(rows) > cap
    rows = rows[:cap]
    buf = io.StringIO()
    cols = ["received_at", "occurred_at", "event_name", "user_id", "anon_id", "session_id", "screen", "referrer_screen",
            "object_type", "object_id", "duration_ms", "platform", "app_version", "channel", "os_version",
            "device_model", "network_type", "props"]
    w = csv.writer(buf)
    w.writerow(cols)
    import json as _json

    for r in rows:
        d = mask_event_row(_row_to_dict(r), unmasked=unmasked)
        w.writerow([_csv_safe(_json.dumps(d[c], ensure_ascii=False) if c == "props" else d.get(c)) for c in cols])
    write_audit(
        db, admin, action="analytics_event_export", target_type="analytics_events",
        target_id=str(user_id) if user_id else (anon_id or session_id or event_name or object_id),
        detail={"reason": reason, "rows": len(rows), "truncated": truncated, "unmasked": unmasked,
                "filters": {"user_id": str(user_id) if user_id else None, "anon_id": anon_id, "session_id": session_id,
                            "event_name": event_name, "screen": screen, "object_id": object_id,
                            "from": start_d.isoformat(), "to": end_d.isoformat()}},
        ip=_ip(request),
    )
    await db.commit()
    filename = f"events_{start_d.isoformat()}_{end_d.isoformat()}.csv"
    return Response(
        content="\ufeff" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "X-Export-Rows": str(len(rows)),
                 "X-Export-Truncated": "1" if truncated else "0"},
    )


def _csv_safe(value: Any) -> Any:
    """Neutralise spreadsheet formula injection."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value
