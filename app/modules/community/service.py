from __future__ import annotations

from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AuditStatus,
    CommunityComment,
    CommunityLike,
    CommunityPost,
    MediaAsset,
    PostStatus,
    User,
    UserProfile,
    UserStatus,
)
from app.shared.errors import AppError
from app.shared.response import ErrorCodes


class MediaItemIn(BaseModel):
    type: str = Field(pattern="^(image|video)$")
    # Prefer media_id after STS upload; url allowed as OSS placeholder for MVP demos
    media_id: UUID | None = None
    url: str | None = Field(default=None, max_length=1024)


class CreatePostRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    media: list[MediaItemIn] = Field(default_factory=list, max_length=9)


class CreateCommentRequest(BaseModel):
    content: str = Field(min_length=1, max_length=1000)


class CommunityService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_post(self, user: User, body: CreatePostRequest) -> dict:
        if user.status == UserStatus.LIMITED.value:
            raise AppError(ErrorCodes.USER_LIMITED, "账号功能受限，无法发帖", status_code=403)
        if not user.profile_completed:
            raise AppError(ErrorCodes.USER_NOT_COMPLETED, "请先完善资料")

        media = await self._normalize_media(user.id, body.media)
        # Always pending until admin review (OSS media_id path reserved for later upload)
        post = CommunityPost(
            id=uuid4(),
            author_id=user.id,
            content=body.content.strip(),
            media=media,
            status=PostStatus.PENDING.value,
        )
        self.db.add(post)
        await self.db.commit()
        await self.db.refresh(post)
        return await self._post_brief(post, viewer_id=user.id)

    async def list_feed(self, user: User, limit: int, offset: int) -> dict:
        result = await self.db.execute(
            select(CommunityPost)
            .where(CommunityPost.status == PostStatus.PUBLISHED.value)
            .order_by(CommunityPost.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        posts = list(result.scalars().all())
        items = [await self._post_brief(p, viewer_id=user.id) for p in posts]
        return {"items": items, "limit": limit, "offset": offset}

    async def list_mine(self, user: User, limit: int, offset: int) -> dict:
        result = await self.db.execute(
            select(CommunityPost)
            .where(
                CommunityPost.author_id == user.id,
                CommunityPost.status != PostStatus.DELETED.value,
            )
            .order_by(CommunityPost.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        posts = list(result.scalars().all())
        items = [await self._post_brief(p, viewer_id=user.id) for p in posts]
        return {"items": items, "limit": limit, "offset": offset}

    async def get_post(self, user: User, post_id: UUID) -> dict:
        post = await self._get_visible_post(post_id, user.id)
        return await self._post_brief(post, viewer_id=user.id)

    async def delete_post(self, user: User, post_id: UUID) -> dict:
        post = await self.db.get(CommunityPost, post_id)
        if post is None or post.status == PostStatus.DELETED.value:
            raise AppError(ErrorCodes.COMMUNITY_NOT_FOUND, "帖子不存在", status_code=404)
        if post.author_id != user.id:
            raise AppError(ErrorCodes.COMMUNITY_FORBIDDEN, "无权删除", status_code=403)
        post.status = PostStatus.DELETED.value
        await self.db.commit()
        return {"deleted": True}

    async def like(self, user: User, post_id: UUID) -> dict:
        post = await self._get_published_post(post_id)
        existing = await self.db.execute(
            select(CommunityLike).where(
                CommunityLike.post_id == post_id,
                CommunityLike.user_id == user.id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return {"liked": True, "like_count": post.like_count}
        self.db.add(CommunityLike(id=uuid4(), post_id=post_id, user_id=user.id))
        post.like_count = int(post.like_count or 0) + 1
        await self.db.commit()
        return {"liked": True, "like_count": post.like_count}

    async def unlike(self, user: User, post_id: UUID) -> dict:
        post = await self._get_published_post(post_id)
        result = await self.db.execute(
            select(CommunityLike).where(
                CommunityLike.post_id == post_id,
                CommunityLike.user_id == user.id,
            )
        )
        row = result.scalar_one_or_none()
        if row is not None:
            await self.db.delete(row)
            post.like_count = max(int(post.like_count or 0) - 1, 0)
            await self.db.commit()
        return {"liked": False, "like_count": post.like_count}

    async def list_comments(self, user: User, post_id: UUID, limit: int, offset: int) -> dict:
        await self._get_visible_post(post_id, user.id)
        result = await self.db.execute(
            select(CommunityComment)
            .where(
                CommunityComment.post_id == post_id,
                CommunityComment.status == "visible",
            )
            .order_by(CommunityComment.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
        rows = list(result.scalars().all())
        items = []
        for c in rows:
            items.append(await self._comment_brief(c))
        return {"items": items, "limit": limit, "offset": offset}

    async def add_comment(self, user: User, post_id: UUID, body: CreateCommentRequest) -> dict:
        if user.status == UserStatus.LIMITED.value:
            raise AppError(ErrorCodes.USER_LIMITED, "账号功能受限，无法评论", status_code=403)
        post = await self._get_published_post(post_id)
        comment = CommunityComment(
            id=uuid4(),
            post_id=post_id,
            author_id=user.id,
            content=body.content.strip(),
            status="visible",
        )
        self.db.add(comment)
        post.comment_count = int(post.comment_count or 0) + 1
        await self.db.commit()
        await self.db.refresh(comment)
        return await self._comment_brief(comment)

    async def _normalize_media(self, user_id: UUID, items: list[MediaItemIn]) -> list[dict]:
        out: list[dict] = []
        for item in items:
            if item.media_id is not None:
                media = await self.db.get(MediaAsset, item.media_id)
                if media is None or media.owner_id != user_id:
                    raise AppError(ErrorCodes.MEDIA_FORBIDDEN, "媒体资源无效")
                if media.audit_status == AuditStatus.REJECTED.value:
                    raise AppError(ErrorCodes.MEDIA_FORBIDDEN, "媒体未通过审核")
                out.append(
                    {
                        "type": item.type,
                        "media_id": str(media.id),
                        "url": media.url,
                        "audit_status": media.audit_status,
                    }
                )
            elif item.url:
                out.append(
                    {
                        "type": item.type,
                        "media_id": None,
                        "url": item.url,
                        "audit_status": "placeholder",
                    }
                )
            else:
                raise AppError(ErrorCodes.COMMUNITY_INVALID, "媒体需提供 media_id 或 url")
        return out

    async def _get_published_post(self, post_id: UUID) -> CommunityPost:
        post = await self.db.get(CommunityPost, post_id)
        if post is None or post.status != PostStatus.PUBLISHED.value:
            raise AppError(ErrorCodes.COMMUNITY_NOT_FOUND, "帖子不存在或未发布", status_code=404)
        return post

    async def _get_visible_post(self, post_id: UUID, viewer_id: UUID) -> CommunityPost:
        post = await self.db.get(CommunityPost, post_id)
        if post is None or post.status == PostStatus.DELETED.value:
            raise AppError(ErrorCodes.COMMUNITY_NOT_FOUND, "帖子不存在", status_code=404)
        if post.status == PostStatus.PUBLISHED.value:
            return post
        if post.author_id == viewer_id:
            return post
        raise AppError(ErrorCodes.COMMUNITY_NOT_FOUND, "帖子不存在或未发布", status_code=404)

    async def _liked(self, post_id: UUID, user_id: UUID) -> bool:
        result = await self.db.execute(
            select(CommunityLike.id).where(
                CommunityLike.post_id == post_id,
                CommunityLike.user_id == user_id,
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _author_brief(self, author_id: UUID) -> dict:
        profile = await self.db.get(UserProfile, author_id)
        return {
            "id": author_id,
            "display_name": (profile.display_name if profile else None) or "用户",
            "avatar_url": None,
        }

    async def _post_brief(self, post: CommunityPost, viewer_id: UUID) -> dict:
        liked = await self._liked(post.id, viewer_id)
        author = await self._author_brief(post.author_id)
        return {
            "id": post.id,
            "author": author,
            "content": post.content,
            "media": post.media or [],
            "status": post.status,
            "like_count": post.like_count,
            "comment_count": post.comment_count,
            "liked": liked,
            "created_at": post.created_at.isoformat() if post.created_at else "",
        }

    async def _comment_brief(self, comment: CommunityComment) -> dict:
        author = await self._author_brief(comment.author_id)
        return {
            "id": comment.id,
            "post_id": comment.post_id,
            "author": author,
            "content": comment.content,
            "created_at": comment.created_at.isoformat() if comment.created_at else "",
        }
