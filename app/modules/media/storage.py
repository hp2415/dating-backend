"""Storage drivers for media uploads.

Client contract is always: sts → PUT upload_url → complete.
Switch STORAGE_DRIVER=local|oss without changing client code.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

from minio import Minio

from app.shared.config import settings
from app.shared.security import create_media_upload_token

logger = logging.getLogger(__name__)

# Magic-number sniffers for common image types (reject masqueraded uploads).
_MAGIC: list[tuple[bytes, str]] = [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
]
_ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
}


def sniff_content_type(data: bytes) -> str | None:
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    for magic, ctype in _MAGIC:
        if data.startswith(magic):
            return ctype
    return None


def validate_upload_bytes(data: bytes, declared_content_type: str) -> None:
    if not data:
        raise ValueError("empty body")
    if len(data) > settings.media_max_upload_bytes:
        raise ValueError("file too large")
    declared = (declared_content_type or "").split(";")[0].strip().lower()
    if declared == "image/jpg":
        declared = "image/jpeg"
    if declared not in _ALLOWED_CONTENT_TYPES:
        raise ValueError(f"unsupported content type: {declared}")
    sniffed = sniff_content_type(data)
    if sniffed is None:
        raise ValueError("unrecognized file magic")
    # jpeg/jpg alias
    if sniffed == "image/jpeg" and declared in {"image/jpeg", "image/jpg"}:
        return
    if sniffed != declared:
        raise ValueError(f"content type mismatch: declared={declared} sniffed={sniffed}")


def safe_object_key(object_key: str) -> str:
    """Reject path traversal; object_key is always server-issued."""
    if not object_key or object_key.startswith("/") or ".." in object_key.split("/"):
        raise ValueError("invalid object_key")
    if "\\" in object_key:
        raise ValueError("invalid object_key")
    return object_key


class StorageDriver(Protocol):
    name: str

    def build_upload(
        self,
        *,
        object_key: str,
        content_type: str,
        owner_id: str,
        public_base: str,
        api_base: str,
    ) -> dict: ...

    def public_url(self, object_key: str, *, public_base: str) -> str: ...

    def exists(self, object_key: str) -> bool: ...

    def save(self, object_key: str, data: bytes) -> None: ...

    def delete(self, object_key: str) -> None: ...


class LocalStorageDriver:
    """Write files under MEDIA_LOCAL_ROOT; nginx or StaticFiles serves /media/."""

    name = "local"

    def __init__(self, root: str | None = None):
        self.root = Path(root or settings.media_local_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, object_key: str) -> Path:
        key = safe_object_key(object_key)
        path = (self.root / key).resolve()
        if not str(path).startswith(str(self.root)):
            raise ValueError("path escape")
        return path

    def build_upload(
        self,
        *,
        object_key: str,
        content_type: str,
        owner_id: str,
        public_base: str,
        api_base: str,
    ) -> dict:
        token = create_media_upload_token(
            owner_id=owner_id,
            object_key=object_key,
            content_type=content_type,
        )
        upload_url = f"{api_base.rstrip('/')}/api/v1/media/upload?token={quote(token, safe='')}"
        return {
            "upload_url": upload_url,
            "object_key": object_key,
            "public_url": self.public_url(object_key, public_base=public_base),
            "method": "PUT",
            "headers": {"Content-Type": content_type},
            "expires_in": settings.media_upload_token_ttl_seconds,
        }

    def public_url(self, object_key: str, *, public_base: str) -> str:
        base = public_base.rstrip("/")
        return f"{base}/media/{safe_object_key(object_key)}"

    def exists(self, object_key: str) -> bool:
        return self._path(object_key).is_file()

    def save(self, object_key: str, data: bytes) -> None:
        path = self._path(object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def delete(self, object_key: str) -> None:
        path = self._path(object_key)
        if path.is_file():
            path.unlink()


class OssStorageDriver:
    """S3-compatible (MinIO / Aliyun OSS) via MinIO client + presigned PUT."""

    name = "oss"

    def _client(self) -> Minio:
        endpoint = settings.oss_endpoint.replace("http://", "").replace("https://", "")
        secure = settings.oss_endpoint.startswith("https://")
        return Minio(
            endpoint,
            access_key=settings.oss_access_key,
            secret_key=settings.oss_secret_key,
            secure=secure,
            region=settings.oss_region,
        )

    def build_upload(
        self,
        *,
        object_key: str,
        content_type: str,
        owner_id: str,
        public_base: str,
        api_base: str,
    ) -> dict:
        _ = owner_id, api_base
        client = self._client()
        try:
            if not client.bucket_exists(settings.oss_bucket):
                client.make_bucket(settings.oss_bucket)
            upload_url = client.presigned_put_object(
                settings.oss_bucket,
                object_key,
                expires=timedelta(minutes=10),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to create OSS STS")
            raise RuntimeError(f"获取上传凭证失败: {exc}") from exc

        public_upload = upload_url.replace(settings.oss_endpoint, settings.oss_public_endpoint)
        return {
            "upload_url": public_upload,
            "object_key": object_key,
            "public_url": self.public_url(object_key, public_base=public_base or settings.oss_public_endpoint),
            "method": "PUT",
            "headers": {"Content-Type": content_type},
            "expires_in": 600,
        }

    def public_url(self, object_key: str, *, public_base: str) -> str:
        # Prefer explicit OSS public endpoint; bucket path matches historical MinIO layout.
        base = (settings.oss_public_endpoint or public_base).rstrip("/")
        return f"{base}/{settings.oss_bucket}/{safe_object_key(object_key)}"

    def exists(self, object_key: str) -> bool:
        try:
            self._client().stat_object(settings.oss_bucket, object_key)
            return True
        except Exception:  # noqa: BLE001
            return False

    def save(self, object_key: str, data: bytes) -> None:
        # OSS path uses client PUT via upload_url; save is for local driver only.
        raise NotImplementedError("OSS upload uses presigned PUT from the client")

    def delete(self, object_key: str) -> None:
        try:
            self._client().remove_object(settings.oss_bucket, object_key)
        except Exception:  # noqa: BLE001
            logger.exception("OSS delete failed for %s", object_key)


def get_storage() -> StorageDriver:
    if settings.storage_driver == "oss":
        return OssStorageDriver()
    return LocalStorageDriver()
