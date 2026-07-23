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
    AuditStatus,
    CommunityPost,
    Match,
    MediaAsset,
    PostStatus,
    Report,
    ReportResolution,
    ReportStatus,
    User,
    UserProfile,
    UserStatus,
)
from app.shared.errors import AppError
from app.shared.response import ErrorCodes

ALLOWED_RESOLUTIONS = {r.value for r in ReportResolution}


class ResolveReportRequest(BaseModel):
    resolution: str
    admin_note: str | None = Field(default=None, max_length=500)


class ReviewMediaRequest(BaseModel):
    action: str  # approve | reject
    admin_note: str | None = Field(default=None, max_length=500)


class ModerationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def dashboard_summary(self, admin: AdminUser) -> dict:
        users_total = int(await self.db.scalar(select(func.count()).select_from(User)) or 0)
        day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        matches_today = int(
            await self.db.scalar(
                select(func.count()).select_from(Match).where(Match.matched_at >= day_start)
            )
            or 0
        )
        reports_pending = int(
            await self.db.scalar(
                select(func.count())
                .select_from(Report)
                .where(Report.status == ReportStatus.PENDING.value)
            )
            or 0
        )
        media_pending = int(
            await self.db.scalar(
                select(func.count())
                .select_from(MediaAsset)
                .where(MediaAsset.audit_status == AuditStatus.PENDING.value)
            )
            or 0
        )
        posts_pending = int(
            await self.db.scalar(
                select(func.count())
                .select_from(CommunityPost)
                .where(CommunityPost.status == PostStatus.PENDING.value)
            )
            or 0
        )
        activities_pending = int(
            await self.db.scalar(
                select(func.count())
                .select_from(Activity)
                .where(Activity.status == ActivityStatus.PENDING.value)
            )
            or 0
        )
        moderation_pending = media_pending + posts_pending + activities_pending
        return {
            "admin": admin.username,
            "role": admin.role,
            "metrics": {
                "users_total": users_total,
                "matches_today": matches_today,
                "reports_pending": reports_pending,
                "moderation_pending": moderation_pending,
                "posts_pending": posts_pending,
                "media_pending": media_pending,
                "activities_pending": activities_pending,
            },
            "notice": "找搭子：活动审核已接入；社区动态并入活动评论",
        }

    async def list_reports(self, status: str | None, limit: int, offset: int) -> dict:
        status = status or ReportStatus.PENDING.value
        stmt = select(Report).order_by(Report.created_at.desc()).offset(offset).limit(limit)
        if status != "all":
            stmt = stmt.where(Report.status == status)
        result = await self.db.execute(stmt)
        rows = list(result.scalars().all())
        items = []
        for r in rows:
            items.append(await self._report_brief(r))
        count_stmt = select(func.count()).select_from(Report)
        if status != "all":
            count_stmt = count_stmt.where(Report.status == status)
        total = int(await self.db.scalar(count_stmt) or 0)
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    async def resolve_report(self, admin: AdminUser, report_id: UUID, body: ResolveReportRequest) -> dict:
        if body.resolution not in ALLOWED_RESOLUTIONS:
            raise AppError(ErrorCodes.MODERATION_INVALID, "无效的处置方式")

        result = await self.db.execute(select(Report).where(Report.id == report_id))
        report = result.scalar_one_or_none()
        if report is None:
            raise AppError(ErrorCodes.REPORT_NOT_FOUND, "举报不存在", status_code=404)
        if report.status != ReportStatus.PENDING.value:
            raise AppError(ErrorCodes.MODERATION_INVALID, "工单已处理", status_code=409)

        target = await self.db.get(User, report.target_user_id)
        if target is None:
            raise AppError(ErrorCodes.USER_NOT_FOUND, "被举报用户不存在", status_code=404)

        now = datetime.now(timezone.utc)
        if body.resolution == ReportResolution.DISMISS.value:
            report.status = ReportStatus.DISMISSED.value
        else:
            report.status = ReportStatus.RESOLVED.value

        report.resolution = body.resolution
        report.resolved_by = admin.id
        report.resolved_at = now
        report.admin_note = body.admin_note

        if body.resolution == ReportResolution.LIMIT.value:
            target.status = UserStatus.LIMITED.value
            target.discoverable = False
        elif body.resolution == ReportResolution.BAN.value:
            target.status = UserStatus.BANNED.value
            target.discoverable = False

        self.db.add(
            AdminAuditLog(
                id=uuid4(),
                admin_id=admin.id,
                action="report_resolve",
                target_type="report",
                target_id=str(report.id),
                detail={
                    "resolution": body.resolution,
                    "target_user_id": str(report.target_user_id),
                    "admin_note": body.admin_note,
                },
            )
        )
        await self.db.commit()
        return await self._report_brief(report)

    async def list_media(self, audit_status: str | None, limit: int, offset: int) -> dict:
        audit_status = audit_status or AuditStatus.PENDING.value
        stmt = select(MediaAsset).order_by(MediaAsset.created_at.desc()).offset(offset).limit(limit)
        if audit_status != "all":
            stmt = stmt.where(MediaAsset.audit_status == audit_status)
        result = await self.db.execute(stmt)
        rows = list(result.scalars().all())
        items = []
        for m in rows:
            owner_name = None
            profile = await self.db.get(UserProfile, m.owner_id)
            if profile:
                owner_name = profile.display_name
            items.append(
                {
                    "id": m.id,
                    "owner_id": m.owner_id,
                    "owner_name": owner_name,
                    "media_type": m.media_type,
                    "url": m.url,
                    "audit_status": m.audit_status,
                    "created_at": m.created_at.isoformat() if m.created_at else "",
                }
            )
        if audit_status == "all":
            total = int(await self.db.scalar(select(func.count()).select_from(MediaAsset)) or 0)
        else:
            total = int(
                await self.db.scalar(
                    select(func.count())
                    .select_from(MediaAsset)
                    .where(MediaAsset.audit_status == audit_status)
                )
                or 0
            )
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    async def review_media(self, admin: AdminUser, media_id: UUID, body: ReviewMediaRequest) -> dict:
        if body.action not in ("approve", "reject"):
            raise AppError(ErrorCodes.MODERATION_INVALID, "无效的审核动作")
        media = await self.db.get(MediaAsset, media_id)
        if media is None:
            raise AppError(ErrorCodes.MODERATION_NOT_FOUND, "媒体不存在", status_code=404)

        media.audit_status = (
            AuditStatus.APPROVED.value if body.action == "approve" else AuditStatus.REJECTED.value
        )
        self.db.add(
            AdminAuditLog(
                id=uuid4(),
                admin_id=admin.id,
                action="media_review",
                target_type="media",
                target_id=str(media.id),
                detail={"action": body.action, "admin_note": body.admin_note},
            )
        )
        await self.db.commit()
        return {
            "id": media.id,
            "audit_status": media.audit_status,
            "action": body.action,
        }

    async def _report_brief(self, report: Report) -> dict:
        reporter_name = None
        target_name = None
        reporter_profile = await self.db.get(UserProfile, report.reporter_id)
        target_profile = await self.db.get(UserProfile, report.target_user_id)
        if reporter_profile:
            reporter_name = reporter_profile.display_name
        if target_profile:
            target_name = target_profile.display_name
        return {
            "id": report.id,
            "reporter_id": report.reporter_id,
            "reporter_name": reporter_name,
            "target_user_id": report.target_user_id,
            "target_name": target_name,
            "reason": report.reason,
            "detail": report.detail,
            "status": report.status,
            "resolution": report.resolution,
            "admin_note": report.admin_note,
            "created_at": report.created_at.isoformat() if report.created_at else "",
            "resolved_at": report.resolved_at.isoformat() if report.resolved_at else None,
        }
