from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
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


class ReportCreate(BaseModel):
    target_user_id: UUID
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
        if user.id == body.target_user_id:
            raise AppError(ErrorCodes.REPORT_INVALID, "不能举报自己")
        if body.reason not in ALLOWED_REASONS:
            raise AppError(ErrorCodes.REPORT_INVALID, "无效的举报原因")

        target = await self.db.get(User, body.target_user_id)
        if target is None or target.status == UserStatus.DELETED.value:
            raise AppError(ErrorCodes.USER_NOT_FOUND, "对方不存在", status_code=404)

        existing = await self.db.execute(
            select(Report).where(
                Report.reporter_id == user.id,
                Report.target_user_id == body.target_user_id,
                Report.status == ReportStatus.PENDING.value,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise AppError(ErrorCodes.REPORT_DUPLICATE, "已有待处理举报", status_code=409)

        report = Report(
            id=uuid4(),
            reporter_id=user.id,
            target_user_id=body.target_user_id,
            reason=body.reason,
            detail=body.detail,
            status=ReportStatus.PENDING.value,
        )
        self.db.add(report)

        blocked = False
        if body.also_block:
            await self._ensure_block(user.id, body.target_user_id)
            blocked = True

        await self.db.commit()
        return {
            "id": report.id,
            "status": report.status,
            "reason": report.reason,
            "blocked": blocked,
        }

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
