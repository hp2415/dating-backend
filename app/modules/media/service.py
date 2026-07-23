import logging
from datetime import timedelta
from uuid import uuid4

from minio import Minio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditStatus, MediaAsset, MediaType, User, UserProfile
from app.shared.config import settings
from app.shared.errors import AppError
from app.shared.response import ErrorCodes

logger = logging.getLogger(__name__)


def _minio_client() -> Minio:
    endpoint = settings.oss_endpoint.replace("http://", "").replace("https://", "")
    secure = settings.oss_endpoint.startswith("https://")
    return Minio(
        endpoint,
        access_key=settings.oss_access_key,
        secret_key=settings.oss_secret_key,
        secure=secure,
        region=settings.oss_region,
    )


class MediaService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_sts(self, user: User, media_type: str, content_type: str, ext: str) -> dict:
        object_key = f"{media_type}/{user.id}/{uuid4().hex}.{ext.lstrip('.')}"
        client = _minio_client()
        try:
            if not client.bucket_exists(settings.oss_bucket):
                client.make_bucket(settings.oss_bucket)
            upload_url = client.presigned_put_object(
                settings.oss_bucket,
                object_key,
                expires=timedelta(minutes=10),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to create STS")
            # Fallback for local/dev when MinIO not reachable from host path differences
            if settings.app_env == "development":
                upload_url = f"{settings.oss_public_endpoint}/{settings.oss_bucket}/{object_key}"
            else:
                raise AppError(ErrorCodes.MEDIA_INVALID, f"获取上传凭证失败: {exc}") from exc

        # Rewrite internal docker hostname for clients outside the compose network
        public_upload = upload_url.replace(settings.oss_endpoint, settings.oss_public_endpoint)
        public_url = f"{settings.oss_public_endpoint}/{settings.oss_bucket}/{object_key}"
        return {
            "upload_url": public_upload,
            "object_key": object_key,
            "public_url": public_url,
            "method": "PUT",
            "headers": {"Content-Type": content_type},
            "expires_in": 600,
        }

    async def complete(self, user: User, object_key: str, media_type: str, set_as_avatar: bool, meta: dict) -> dict:
        if not object_key.startswith(f"{media_type}/{user.id}/"):
            raise AppError(ErrorCodes.MEDIA_FORBIDDEN, "object_key 不属于当前用户")

        # MVP: auto-approve in development; production should enqueue moderation worker
        audit = AuditStatus.APPROVED.value if settings.app_env == "development" else AuditStatus.PENDING.value
        url = f"{settings.oss_public_endpoint}/{settings.oss_bucket}/{object_key}"
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
