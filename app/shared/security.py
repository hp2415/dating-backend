from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import jwt

from app.shared.config import settings


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(*, user_id: str, extra: dict[str, Any] | None = None) -> str:
    payload: dict[str, Any] = {
        "sub": user_id,
        "type": "access",
        "iat": _now(),
        "exp": _now() + timedelta(minutes=settings.jwt_access_ttl_minutes),
        "jti": str(uuid4()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_refresh_token(*, user_id: str) -> tuple[str, str]:
    jti = str(uuid4())
    payload = {
        "sub": user_id,
        "type": "refresh",
        "iat": _now(),
        "exp": _now() + timedelta(days=settings.jwt_refresh_ttl_days),
        "jti": jti,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return token, jti


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


def create_media_upload_token(
    *,
    owner_id: str,
    object_key: str,
    content_type: str,
) -> str:
    """Short-lived token for PUT /api/v1/media/upload (no Authorization header needed)."""
    payload = {
        "sub": owner_id,
        "type": "media_upload",
        "object_key": object_key,
        "content_type": content_type,
        "iat": _now(),
        "exp": _now() + timedelta(seconds=settings.media_upload_token_ttl_seconds),
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_media_upload_token(token: str) -> dict[str, Any]:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    if payload.get("type") != "media_upload":
        raise jwt.InvalidTokenError("not a media upload token")
    return payload


def create_admin_access_token(*, admin_id: str, role: str, username: str) -> str:
    payload = {
        "sub": admin_id,
        "type": "admin_access",
        "role": role,
        "username": username,
        "iat": _now(),
        "exp": _now() + timedelta(minutes=settings.admin_jwt_ttl_minutes),
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, settings.admin_jwt_secret, algorithm="HS256")


def decode_admin_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.admin_jwt_secret, algorithms=["HS256"])
