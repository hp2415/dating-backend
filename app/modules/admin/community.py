from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AdminAuditLog,
    AdminUser,
    CommunityPost,
    PostStatus,
    UserProfile,
)
from app.shared.errors import AppError
from app.shared.response import ErrorCodes


class ReviewPostRequest(BaseModel):
    action: str  # approve | reject
    admin_note: str | None = Field(default=None, max_length=500)


class CommunityAdminService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_posts(self, status: str | None, limit: int, offset: int) -> dict:
        status = status or PostStatus.PENDING.value
        stmt = select(CommunityPost).order_by(CommunityPost.created_at.desc()).offset(offset).limit(limit)
        if status != "all":
            stmt = stmt.where(CommunityPost.status == status)
        result = await self.db.execute(stmt)
        rows = list(result.scalars().all())
        items = [await self._brief(p) for p in rows]
        count_stmt = select(func.count()).select_from(CommunityPost)
        if status != "all":
            count_stmt = count_stmt.where(CommunityPost.status == status)
        total = int(await self.db.scalar(count_stmt) or 0)
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    async def review_post(self, admin: AdminUser, post_id: UUID, body: ReviewPostRequest) -> dict:
        if body.action not in ("approve", "reject"):
            raise AppError(ErrorCodes.MODERATION_INVALID, "无效的审核动作")
        post = await self.db.get(CommunityPost, post_id)
        if post is None or post.status == PostStatus.DELETED.value:
            raise AppError(ErrorCodes.COMMUNITY_NOT_FOUND, "帖子不存在", status_code=404)
        if post.status != PostStatus.PENDING.value:
            raise AppError(ErrorCodes.MODERATION_INVALID, "帖子已审核", status_code=409)

        post.status = PostStatus.PUBLISHED.value if body.action == "approve" else PostStatus.REJECTED.value
        post.reviewed_by = admin.id
        post.reviewed_at = datetime.now(timezone.utc)
        post.admin_note = body.admin_note
        self.db.add(
            AdminAuditLog(
                id=uuid4(),
                admin_id=admin.id,
                action="community_post_review",
                target_type="community_post",
                target_id=str(post.id),
                detail={"action": body.action, "admin_note": body.admin_note},
            )
        )
        await self.db.commit()
        return await self._brief(post)

    async def pending_count(self) -> int:
        return int(
            await self.db.scalar(
                select(func.count())
                .select_from(CommunityPost)
                .where(CommunityPost.status == PostStatus.PENDING.value)
            )
            or 0
        )

    async def _brief(self, post: CommunityPost) -> dict:
        profile = await self.db.get(UserProfile, post.author_id)
        return {
            "id": post.id,
            "author_id": post.author_id,
            "author_name": (profile.display_name if profile else None),
            "content": post.content,
            "media": post.media or [],
            "status": post.status,
            "like_count": post.like_count,
            "comment_count": post.comment_count,
            "admin_note": post.admin_note,
            "created_at": post.created_at.isoformat() if post.created_at else "",
            "reviewed_at": post.reviewed_at.isoformat() if post.reviewed_at else None,
        }
