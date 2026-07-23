from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminUser
from app.modules.admin.seed import write_audit
from app.shared.config import settings
from app.shared.errors import AppError
from app.shared.passwords import verify_password
from app.shared.response import ErrorCodes
from app.shared.security import create_admin_access_token

# Simple permission map by role for skeleton stage
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "superadmin": ["*"],
    "auditor": ["user:read", "moderation:read", "moderation:write", "report:read", "report:write"],
    "operator": ["user:read", "config:read", "config:write", "dashboard:read"],
    "support": ["user:read", "report:read", "report:write"],
    "readonly": ["user:read", "dashboard:read", "report:read"],
}


class AdminAuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def login(self, username: str, password: str, ip: str | None = None) -> dict:
        result = await self.db.execute(select(AdminUser).where(AdminUser.username == username))
        admin = result.scalar_one_or_none()
        if admin is None or not verify_password(password, admin.password_hash):
            raise AppError(ErrorCodes.ADMIN_INVALID_CREDENTIALS, "用户名或密码错误", status_code=401)
        if not admin.is_active:
            raise AppError(ErrorCodes.ADMIN_DISABLED, "账号已停用", status_code=403)

        admin.last_login_at = datetime.now(timezone.utc)
        token = create_admin_access_token(
            admin_id=str(admin.id),
            role=admin.role,
            username=admin.username,
        )
        await self.db.flush()
        await write_audit(
            self.db,
            admin_id=admin.id,
            action="admin_login",
            target_type="admin_user",
            target_id=str(admin.id),
            detail={"username": admin.username},
            ip=ip,
        )
        return {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": settings.admin_jwt_ttl_minutes * 60,
            "admin": {
                "id": admin.id,
                "username": admin.username,
                "display_name": admin.display_name,
                "role": admin.role,
                "is_active": admin.is_active,
            },
        }

    async def me(self, admin: AdminUser) -> dict:
        return {
            "id": admin.id,
            "username": admin.username,
            "display_name": admin.display_name,
            "role": admin.role,
            "permissions": ROLE_PERMISSIONS.get(admin.role, []),
            "last_login_at": admin.last_login_at.isoformat() if admin.last_login_at else None,
        }
