"""Media service: STS → upload → complete; album list/delete."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditStatus, MediaAsset, MediaType, ModerationMachineLabel, User, UserProfile
from app.modules.media.storage import get_storage, safe_object_key, validate_upload_bytes
from app.modules.trust.service import TrustService
from app.shared.config import settings
from app.shared.errors import AppError
from app.shared.response import ErrorCodes
from app.shared.security import decode_media_upload_token

logger = logging.getLogger(__name__)


def _resolve_public_base(request_base: str | None) -> str:
    if settings.media_public_base:
        return settings.media_public_base.rstrip("/")
    if request_base:
        return request_base.rstrip("/")
    if settings.storage_driver == "oss":
        return settings.oss_public_endpoint.rstrip("/")
    return "http://localhost:8000"


def _resolve_api_base(request_base: str | None) -> str:
    # Upload endpoint is always on the API host (same as public_base for local).
    return _resolve_public_base(request_base)


class MediaService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.storage = get_storage()

    async def create_sts(
        self,
        user: User,
        media_type: str,
        content_type: str,
        ext: str,
        *,
        request_base: str | None = None,
    ) -> dict:
        object_key = f"{media_type}/{user.id}/{uuid4().hex}.{ext.lstrip('.')}"
        public_base = _resolve_public_base(request_base)
        api_base = _resolve_api_base(request_base)
        try:
            return self.storage.build_upload(
                object_key=object_key,
                content_type=content_type,
                owner_id=str(user.id),
                public_base=public_base,
                api_base=api_base,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to create STS")
            raise AppError(ErrorCodes.MEDIA_INVALID, f"获取上传凭证失败: {exc}") from exc

    async def save_upload(self, token: str, body: bytes) -> dict:
        try:
            claims = decode_media_upload_token(token)
        except Exception as exc:  # noqa: BLE001
            raise AppError(ErrorCodes.MEDIA_FORBIDDEN, "上传令牌无效或已过期", status_code=401) from exc

        object_key = safe_object_key(str(claims["object_key"]))
        content_type = str(claims.get("content_type") or "application/octet-stream")
        try:
            validate_upload_bytes(body, content_type)
        except ValueError as exc:
            raise AppError(ErrorCodes.MEDIA_INVALID, str(exc)) from exc

        if settings.storage_driver != "local":
            raise AppError(ErrorCodes.MEDIA_INVALID, "当前存储驱动不支持直传端点")

        try:
            self.storage.save(object_key, body)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to save upload")
            raise AppError(ErrorCodes.MEDIA_INVALID, f"保存失败: {exc}") from exc

        return {"object_key": object_key, "bytes": len(body)}

    async def complete(
        self,
        user: User,
        object_key: str,
        media_type: str,
        set_as_avatar: bool,
        meta: dict,
        *,
        request_base: str | None = None,
    ) -> dict:
        object_key = safe_object_key(object_key)
        if not object_key.startswith(f"{media_type}/{user.id}/"):
            raise AppError(ErrorCodes.MEDIA_FORBIDDEN, "object_key 不属于当前用户")

        if not self.storage.exists(object_key):
            raise AppError(ErrorCodes.MEDIA_INVALID, "文件未上传成功")

        auto = settings.media_auto_approve
        audit = AuditStatus.APPROVED.value if auto else AuditStatus.PENDING.value
        public_base = _resolve_public_base(request_base)
        url = self.storage.public_url(object_key, public_base=public_base)

        media = MediaAsset(
            id=uuid4(),
            owner_id=user.id,
            media_type=media_type,
            object_key=object_key,
            url=url,
            audit_status=audit,
            meta=meta or {},
        )
        self.db.add(media)
        await self.db.flush()

        if not auto:
            await TrustService(self.db).enqueue_moderation_task(
                target_kind="media",
                target_id=media.id,
                machine_label=ModerationMachineLabel.REVIEW.value,
                payload={"media_type": media_type, "object_key": object_key, "url": url},
                priority=1 if media_type == MediaType.AVATAR.value else 0,
            )

        if set_as_avatar or media_type == MediaType.AVATAR.value:
            profile = await self.db.get(UserProfile, user.id)
            if profile is None:
                profile = UserProfile(user_id=user.id, tags=[])
                self.db.add(profile)
            profile.avatar_media_id = media.id

        await self.db.commit()
        await self.db.refresh(media)
        return {
            "id": media.id,
            "url": media.url,
            "media_type": media.media_type,
            "audit_status": media.audit_status,
            "object_key": media.object_key,
        }

    async def list_mine(
        self,
        user: User,
        *,
        media_type: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict], int]:
        filters = [
            MediaAsset.owner_id == user.id,
            MediaAsset.deleted_at.is_(None),
        ]
        if media_type:
            filters.append(MediaAsset.media_type == media_type)

        count_q = select(func.count()).select_from(MediaAsset).where(*filters)
        total = int((await self.db.execute(count_q)).scalar_one())
        rows = (
            await self.db.execute(
                select(MediaAsset)
                .where(*filters)
                .order_by(MediaAsset.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()
        items = [
            {
                "id": m.id,
                "url": m.url,
                "media_type": m.media_type,
                "audit_status": m.audit_status,
                "object_key": m.object_key,
                "meta": m.meta or {},
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in rows
        ]
        return items, total

    async def soft_delete(self, user: User, media_id: UUID) -> dict:
        media = await self.db.get(MediaAsset, media_id)
        if media is None or media.deleted_at is not None:
            raise AppError(ErrorCodes.MEDIA_INVALID, "媒体不存在", status_code=404)
        if media.owner_id != user.id:
            raise AppError(ErrorCodes.MEDIA_FORBIDDEN, "无权删除", status_code=403)

        media.deleted_at = datetime.now(timezone.utc)
        # Clear avatar pointer if this was the avatar
        profile = await self.db.get(UserProfile, user.id)
        if profile and profile.avatar_media_id == media.id:
            profile.avatar_media_id = None

        await self.db.commit()
        return {"id": media.id, "deleted": True}
