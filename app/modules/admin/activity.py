from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Activity,
    ActivityStatus,
    AdminAuditLog,
    AdminUser,
    UserProfile,
)
from app.shared.errors import AppError
from app.shared.response import ErrorCodes


class ReviewActivityRequest(BaseModel):
    action: str  # approve | reject
    admin_note: str | None = Field(default=None, max_length=500)


class ActivityAdminService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_activities(self, status: str | None, limit: int, offset: int) -> dict:
        status = status or ActivityStatus.PENDING.value
        stmt = select(Activity).order_by(Activity.created_at.desc()).offset(offset).limit(limit)
        if status != "all":
            stmt = stmt.where(Activity.status == status)
        result = await self.db.execute(stmt)
        rows = list(result.scalars().all())
        items = [await self._brief(a) for a in rows]
        count_stmt = select(func.count()).select_from(Activity)
        if status != "all":
            count_stmt = count_stmt.where(Activity.status == status)
        total = int(await self.db.scalar(count_stmt) or 0)
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    async def review(self, admin: AdminUser, activity_id: UUID, body: ReviewActivityRequest) -> dict:
        if body.action not in ("approve", "reject"):
            raise AppError(ErrorCodes.MODERATION_INVALID, "无效的审核动作")
        activity = await self.db.get(Activity, activity_id)
        if activity is None or activity.status == ActivityStatus.CANCELLED.value:
            raise AppError(ErrorCodes.ACTIVITY_NOT_FOUND, "活动不存在", status_code=404)
        if activity.status != ActivityStatus.PENDING.value:
            raise AppError(ErrorCodes.MODERATION_INVALID, "活动已审核", status_code=409)

        activity.status = (
            ActivityStatus.PUBLISHED.value if body.action == "approve" else ActivityStatus.REJECTED.value
        )
        activity.reviewed_by = admin.id
        activity.reviewed_at = datetime.now(timezone.utc)
        activity.admin_note = body.admin_note
        self.db.add(
            AdminAuditLog(
                id=uuid4(),
                admin_id=admin.id,
                action="activity_review",
                target_type="activity",
                target_id=str(activity.id),
                detail={"action": body.action, "admin_note": body.admin_note},
            )
        )
        await self.db.commit()
        return await self._brief(activity)

    async def _brief(self, activity: Activity) -> dict:
        profile = await self.db.get(UserProfile, activity.host_id)
        return {
            "id": activity.id,
            "host_id": activity.host_id,
            "host_name": (profile.display_name if profile else None),
            "title": activity.title,
            "description": activity.description,
            "category": activity.category,
            "city": activity.city,
            "address": activity.address,
            "start_at": activity.start_at.isoformat() if activity.start_at else None,
            "capacity": activity.capacity,
            "join_count": activity.join_count,
            "media": activity.media or [],
            "status": activity.status,
            "admin_note": activity.admin_note,
            "created_at": activity.created_at.isoformat() if activity.created_at else "",
            "reviewed_at": activity.reviewed_at.isoformat() if activity.reviewed_at else None,
        }
