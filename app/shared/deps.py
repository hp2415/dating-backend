from collections.abc import AsyncGenerator
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import User, UserStatus
from app.shared.db import SessionLocal
from app.shared.errors import AppError
from app.shared.response import ErrorCodes
from app.shared.security import decode_token

bearer_scheme = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


def get_request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise AppError(ErrorCodes.AUTH_UNAUTHORIZED, "未登录", status_code=401)
    try:
        payload = decode_token(credentials.credentials)
    except Exception as exc:  # noqa: BLE001
        raise AppError(ErrorCodes.AUTH_TOKEN_INVALID, "令牌无效或已过期", status_code=401) from exc

    if payload.get("type") != "access":
        raise AppError(ErrorCodes.AUTH_TOKEN_INVALID, "令牌类型错误", status_code=401)

    user_id = payload.get("sub")
    try:
        uid = UUID(user_id)
    except Exception as exc:  # noqa: BLE001
        raise AppError(ErrorCodes.AUTH_TOKEN_INVALID, "令牌无效", status_code=401) from exc

    result = await db.execute(
        select(User)
        .where(User.id == uid)
        .options(selectinload(User.profile), selectinload(User.preference))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise AppError(ErrorCodes.USER_NOT_FOUND, "用户不存在", status_code=404)
    if user.status == UserStatus.BANNED.value:
        raise AppError(ErrorCodes.AUTH_BANNED, "账号已被封禁", status_code=403)
    if user.status == UserStatus.DELETED.value:
        raise AppError(ErrorCodes.AUTH_UNAUTHORIZED, "账号已注销", status_code=401)
    return user
