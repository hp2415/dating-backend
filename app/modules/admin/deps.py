from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminUser
from app.shared.db import SessionLocal
from app.shared.deps import get_db
from app.shared.errors import AppError
from app.shared.response import ErrorCodes
from app.shared.security import decode_admin_token

admin_bearer = HTTPBearer(auto_error=False)


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(admin_bearer),
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    if credentials is None or not credentials.credentials:
        raise AppError(ErrorCodes.ADMIN_UNAUTHORIZED, "未登录管理后台", status_code=401)
    try:
        payload = decode_admin_token(credentials.credentials)
    except Exception as exc:  # noqa: BLE001
        raise AppError(ErrorCodes.ADMIN_UNAUTHORIZED, "管理端令牌无效或已过期", status_code=401) from exc

    if payload.get("type") != "admin_access":
        raise AppError(ErrorCodes.ADMIN_UNAUTHORIZED, "令牌类型错误", status_code=401)

    try:
        admin_id = UUID(payload.get("sub"))
    except Exception as exc:  # noqa: BLE001
        raise AppError(ErrorCodes.ADMIN_UNAUTHORIZED, "令牌无效", status_code=401) from exc

    result = await db.execute(select(AdminUser).where(AdminUser.id == admin_id))
    admin = result.scalar_one_or_none()
    if admin is None:
        raise AppError(ErrorCodes.ADMIN_UNAUTHORIZED, "管理员不存在", status_code=401)
    if not admin.is_active:
        raise AppError(ErrorCodes.ADMIN_DISABLED, "账号已停用", status_code=403)
    return admin
