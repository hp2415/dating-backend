"""Ops metrics and audit-log reads. Permission: dashboard:read."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminAuditLog
from app.modules.metrics.service import MetricsService, SHANGHAI


class InsightsService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.metrics = MetricsService(db)

    async def overview(self, days: int) -> dict:
        return await self.metrics.overview(days)

    async def funnel(self, name: str, day_from: date | None, day_to: date | None) -> dict:
        today = datetime.now(SHANGHAI).date()
        start = day_from or (today - timedelta(days=6))
        end = day_to or today
        if end < start:
            start, end = end, start
        return await self.metrics.funnel(name, start, end)

    async def retention(self, cohort: date | None) -> dict:
        day = cohort or (datetime.now(SHANGHAI).date() - timedelta(days=1))
        return await self.metrics.retention(day)

    async def rebuild(self, days: int) -> dict:
        rows = await self.metrics.rebuild_recent(days)
        await self.db.commit()
        return {"rebuilt": len(rows), "days": rows}

    async def audit_logs(
        self,
        *,
        admin_id: UUID | None,
        action: str | None,
        target_type: str | None,
        day_from: date | None,
        day_to: date | None,
        limit: int,
        offset: int,
    ) -> dict:
        filters = []
        if admin_id is not None:
            filters.append(AdminAuditLog.admin_id == admin_id)
        if action:
            filters.append(AdminAuditLog.action == action)
        if target_type:
            filters.append(AdminAuditLog.target_type == target_type)
        if day_from is not None:
            start = datetime.combine(day_from, time.min, tzinfo=SHANGHAI)
            filters.append(AdminAuditLog.created_at >= start)
        if day_to is not None:
            end = datetime.combine(day_to + timedelta(days=1), time.min, tzinfo=SHANGHAI)
            filters.append(AdminAuditLog.created_at < end)
        from sqlalchemy import func

        count_stmt = select(func.count()).select_from(AdminAuditLog)
        list_stmt = select(AdminAuditLog).order_by(AdminAuditLog.created_at.desc())
        if filters:
            count_stmt = count_stmt.where(*filters)
            list_stmt = list_stmt.where(*filters)
        total = int(await self.db.scalar(count_stmt) or 0)
        rows = list((await self.db.execute(list_stmt.limit(limit).offset(offset))).scalars().all())
        return {
            "items": [_audit_brief(row) for row in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


def _audit_brief(row: AdminAuditLog) -> dict:
    created = row.created_at
    if created is not None and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return {
        "id": str(row.id),
        "admin_id": str(row.admin_id) if row.admin_id else None,
        "action": row.action,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "detail": row.detail or {},
        "ip": row.ip,
        "created_at": created.isoformat() if created else None,
    }
