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
