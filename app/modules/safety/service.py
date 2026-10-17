from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Block,
    Match,
    MatchStatus,
    Report,
    ReportReason,
    ReportStatus,
    User,
    UserStatus,
)
from app.modules.discover.service import DiscoverService, _ordered_pair
from app.shared.errors import AppError
from app.shared.response import ErrorCodes

ALLOWED_REASONS = {r.value for r in ReportReason}
# 客户端展示用中文原因 → 规范原因码
REASON_ALIASES = {
    "骚扰辱骂": "harassment",
    "骚扰": "harassment",
    "欺诈广告": "spam",
    "垃圾广告": "spam",
    "色情低俗": "inappropriate",
    "违规内容": "inappropriate",
    "虚假信息": "fake",
    "冒充": "fake",
    "其他": "other",
}
TARGET_KINDS = {"user", "post", "comment", "activity", "club", "guild", "conversation", "message"}
DAILY_REPORT_LIMIT = 20


class ReportCreate(BaseModel):
    id: UUID | None = Field(default=None, description="客户端预生成工单 ID（离线重试幂等）")
    target_user_id: UUID | None = None
    target_kind: str = "user"
    target_id: str | None = Field(default=None, max_length=64)
    title: str | None = Field(default=None, max_length=80, description="被举报对象标题/昵称，写入快照")
    reason: str
    detail: str | None = Field(default=None, max_length=500)
    also_block: bool = False


class BlockCreate(BaseModel):
    target_user_id: UUID


class SafetyService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.discover = DiscoverService(db)

    async def create_report(self, user: User, body: ReportCreate) -> dict:
        if body.id is not None:
            prior = await self.db.get(Report, body.id)
            if prior is not None:
                if prior.reporter_id != user.id:
                    raise AppError(ErrorCodes.REPORT_INVALID, "ID 已被占用", status_code=409)
                return {
                    "id": prior.id,
                    "status": prior.status,
                    "reason": prior.reason,
                    "target_kind": prior.target_kind,
                    "target_id": prior.target_id,
                    "blocked": False,
                }
        kind = (body.target_kind or "user").strip().lower()
        if kind not in TARGET_KINDS:
            raise AppError(ErrorCodes.REPORT_INVALID, "不支持的举报对象类型")
        reason = REASON_ALIASES.get(body.reason, body.reason)
        detail = body.detail
        if reason not in ALLOWED_REASONS:
            if body.reason and len(body.reason) <= 40:
                # 客户端自定义文案：归入 other 并保留原文
                detail = " · ".join(x for x in (body.reason, body.detail) if x)[:500]
                reason = "other"
            else:
                raise AppError(ErrorCodes.REPORT_INVALID, "无效的举报原因")

        target_user_id = body.target_user_id
        target_id = (body.target_id or "").strip() or (str(target_user_id) if target_user_id else "")
        if not target_id:
            raise AppError(ErrorCodes.REPORT_INVALID, "缺少举报对象")
        if kind == "user":
            try:
                target_user_id = target_user_id or UUID(target_id)
            except ValueError as exc:
                raise AppError(ErrorCodes.REPORT_INVALID, "无效的用户 ID") from exc
            target_id = str(target_user_id)

        if target_user_id is not None and user.id == target_user_id:
            raise AppError(ErrorCodes.REPORT_INVALID, "不能举报自己")

        since = datetime.now(timezone.utc) - timedelta(days=1)
        today = await self.db.scalar(
            select(func.count()).select_from(Report).where(Report.reporter_id == user.id, Report.created_at >= since)
        )
        if int(today or 0) >= DAILY_REPORT_LIMIT:
            raise AppError(ErrorCodes.REPORT_INVALID, "今日举报次数已达上限", status_code=429)

        snapshot: dict = {"title": (body.title or "")[:80]}
        owner_id, exists, title = await self._resolve_target(kind, target_id)
        snapshot["exists"] = exists
        if title and not snapshot["title"]:
            snapshot["title"] = title[:80]
        if kind == "user":
            target = await self.db.get(User, target_user_id)
            if target is None or target.status == UserStatus.DELETED.value:
                raise AppError(ErrorCodes.USER_NOT_FOUND, "对方不存在", status_code=404)
        elif target_user_id is None and owner_id is not None and owner_id != user.id:
            target_user_id = owner_id  # 便于运营直接对责任人处置

        existing = await self.db.execute(
            select(Report.id).where(
                Report.reporter_id == user.id,
                Report.target_kind == kind,
                Report.target_id == target_id,
                Report.status == ReportStatus.PENDING.value,
            )
        )
        if existing.first() is not None:
            raise AppError(ErrorCodes.REPORT_DUPLICATE, "已有待处理举报", status_code=409)

        report = Report(
            id=body.id or uuid4(),
            reporter_id=user.id,
            target_user_id=target_user_id,
            target_kind=kind,
            target_id=target_id,
            snapshot=snapshot,
            reason=reason,
            detail=detail,
            status=ReportStatus.PENDING.value,
        )
        self.db.add(report)

        blocked = False
        if body.also_block and target_user_id is not None:
            await self._ensure_block(user.id, target_user_id)
            blocked = True

        await self.db.commit()
        return {
            "id": report.id,
            "status": report.status,
            "reason": report.reason,
            "target_kind": kind,
            "target_id": target_id,
            "blocked": blocked,
        }

    async def _resolve_target(self, kind: str, target_id: str) -> tuple[UUID | None, bool, str | None]:
        """Return (owner user id, exists, title) — best effort, never raises."""
        try:
            tid = UUID(target_id)
        except ValueError:
            return None, False, None
        from app.models import Activity, ActivityComment, Club, CommunityPost, Conversation, Guild

        try:
            if kind == "post":
                row = await self.db.get(CommunityPost, tid)
                return (row.author_id, True, (row.content or "")[:40]) if row else (None, False, None)
            if kind == "activity":
                row = await self.db.get(Activity, tid)
                return (row.host_id, True, row.title) if row else (None, False, None)
            if kind == "comment":
                row = await self.db.get(ActivityComment, tid)
                return (row.author_id, True, (row.content or "")[:40]) if row else (None, False, None)
            if kind == "club":
                row = await self.db.get(Club, tid)
                return (row.creator_id, True, row.name) if row else (None, False, None)
            if kind == "guild":
                row = await self.db.get(Guild, tid)
                return (row.owner_user_id, True, row.name) if row else (None, False, None)
            if kind == "conversation":
                row = await self.db.get(Conversation, tid)
                return (None, True, row.title) if row else (None, False, None)
        except Exception:  # noqa: BLE001  (column name drift must not break reporting)
            return None, False, None
        return None, False, None

    async def list_my_reports(self, user: User, *, limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
        total = int(
            await self.db.scalar(select(func.count()).select_from(Report).where(Report.reporter_id == user.id)) or 0
        )
        rows = (
            await self.db.execute(
                select(Report)
                .where(Report.reporter_id == user.id)
                .order_by(Report.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()
        items = [
            {
                "id": str(r.id),
                "target_kind": r.target_kind,
                "target_id": r.target_id,
                "title": (r.snapshot or {}).get("title", ""),
                "reason": r.reason,
                "detail": r.detail,
                "status": r.status,
                "resolution": r.resolution,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
            }
            for r in rows
        ]
        return items, total

    async def create_block(self, user: User, target_user_id: UUID) -> dict:
        if user.id == target_user_id:
            raise AppError(ErrorCodes.BLOCK_INVALID, "不能拉黑自己")
        target = await self.db.get(User, target_user_id)
        if target is None or target.status == UserStatus.DELETED.value:
            raise AppError(ErrorCodes.USER_NOT_FOUND, "对方不存在", status_code=404)

        created = await self._ensure_block(user.id, target_user_id)
        await self.db.commit()
        return {"blocked": True, "created": created}

    async def delete_block(self, user: User, target_user_id: UUID) -> dict:
        result = await self.db.execute(
            select(Block).where(Block.blocker_id == user.id, Block.blocked_id == target_user_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise AppError(ErrorCodes.BLOCK_NOT_FOUND, "未拉黑该用户", status_code=404)
        await self.db.delete(row)
        await self.db.commit()
        return {"unblocked": True}

    async def list_blocks(self, user: User) -> list[dict]:
        result = await self.db.execute(
            select(Block).where(Block.blocker_id == user.id).order_by(Block.created_at.desc())
        )
        blocks = list(result.scalars().all())
        items = []
        for b in blocks:
            peer = await self.db.execute(
                select(User)
                .where(User.id == b.blocked_id)
                .options(selectinload(User.profile), selectinload(User.preference))
            )
            peer_user = peer.scalar_one_or_none()
            if peer_user is None:
                continue
            card = await self.discover._to_card(peer_user)
            items.append(
                {
                    "user_id": b.blocked_id,
                    "blocked_at": b.created_at.isoformat() if b.created_at else "",
                    "peer": card,
                }
            )
        return items

    async def _ensure_block(self, blocker_id: UUID, blocked_id: UUID) -> bool:
        existing = await self.db.execute(
            select(Block).where(Block.blocker_id == blocker_id, Block.blocked_id == blocked_id)
        )
        if existing.scalar_one_or_none() is not None:
            await self._cascade_match_blocked(blocker_id, blocked_id)
            return False

        self.db.add(
            Block(
                id=uuid4(),
                blocker_id=blocker_id,
                blocked_id=blocked_id,
            )
        )
        await self._cascade_match_blocked(blocker_id, blocked_id)
        return True

    async def _cascade_match_blocked(self, a: UUID, b: UUID) -> None:
        low, high = _ordered_pair(a, b)
        result = await self.db.execute(
            select(Match).where(
                Match.user_low == low,
                Match.user_high == high,
                Match.status == MatchStatus.ACTIVE.value,
            )
        )
        match = result.scalar_one_or_none()
        if match is not None:
            match.status = MatchStatus.BLOCKED.value
            match.unmatched_at = datetime.now(timezone.utc)


async def is_blocked_either(db: AsyncSession, a: UUID, b: UUID) -> bool:
    result = await db.execute(
        select(Block.id).where(
            or_(
                and_(Block.blocker_id == a, Block.blocked_id == b),
                and_(Block.blocker_id == b, Block.blocked_id == a),
            )
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None
