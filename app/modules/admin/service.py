from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminUser
from app.modules.admin.seed import write_audit
from app.shared.config import settings
from app.shared.errors import AppError
from app.shared.passwords import hash_password, verify_password
from app.shared.response import ErrorCodes
from app.shared.security import create_admin_access_token

# Permission codes: <resource>:<action>. superadmin has "*".
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "superadmin": ["*"],
    "auditor": [
        "dashboard:read",
        "user:read",
        "user:write",
        "moderation:read",
        "moderation:write",
        "report:read",
        "report:write",
        "activity:read",
        "activity:review",
        "community:read",
        "community:review",
        "media:read",
        "media:review",
        "order:read",
        "chat:read",
        "companion:read",
        "companion:review",
        "trust:read",
        "trust:write",
        "verification:review",
        "club:read",
        "club:write",
    ],
    "operator": [
        "dashboard:read",
        "analytics:read",
        "user:read",
        "activity:read",
        "community:read",
        "media:read",
        "config:read",
        "config:write",
        "report:read",
        "order:read",
        "chat:read",
        "companion:read",
        "trust:read",
        "push:write",
        "club:read",
        "club:write",
    ],
    "support": [
        "dashboard:read",
        "analytics:events",
        "analytics:pii",
        "user:read",
        "user:write",
        "report:read",
        "report:write",
        "activity:read",
        "community:read",
        "order:read",
        "order:refund",
        "chat:read",
        "companion:read",
        "trust:read",
        "sanction:write",
        "club:read",
    ],
    "readonly": [
        "dashboard:read",
        "user:read",
        "report:read",
        "activity:read",
        "community:read",
        "media:read",
        "moderation:read",
        "order:read",
        "chat:read",
        "companion:read",
        "trust:read",
        "config:read",
        "club:read",
    ],
    "finance": [
        "dashboard:read",
        "order:read",
        "order:write",
        "order:refund",
        "user:read",
        "companion:read",
    ],
    # 数据分析：只读。能看聚合看板、查询/导出脱敏后的事件；不能看明文用户标识，不能改任何业务数据。
    "analyst": [
        "dashboard:read",
        "analytics:read",
        "analytics:events",
        "analytics:export",
        "analytics:rebuild",
        "activity:read",
        "community:read",
        "companion:read",
        "club:read",
    ],
}

# One platform, several hats. Keys are stable (stored in admin_users.role); labels are what people see.
ROLE_META: dict[str, dict[str, str]] = {
    "superadmin": {"label": "超级管理员", "desc": "全部权限，含管理员账号、审计日志、明文用户标识与数据导出。"},
    "operator": {"label": "运营", "desc": "活动 / 俱乐部 / 推送 / 运营配置；可看数据看板（聚合，不含用户级事件）。"},
    "auditor": {"label": "内容审核员", "desc": "内容审核、举报处置、信任与认证审核；不含运营配置与数据看板。"},
    "support": {"label": "客服", "desc": "用户查询、举报与退款、封禁；可按用户查看行为事件用于排障（全程审计）。"},
    "finance": {"label": "财务", "desc": "订单 / 钱包 / 退款与对账；只读用户与陪玩基础信息。"},
    "analyst": {"label": "数据分析（只读）", "desc": "聚合看板、漏斗、留存；事件查询与导出默认脱敏，需填写用途并留痕。"},
    "readonly": {"label": "只读访客", "desc": "运营后台基础模块只读，无数据分析与事件权限。"},
}

PERMISSION_LABELS: dict[str, str] = {
    "analytics:read": "查看数据看板（聚合）",
    "analytics:events": "查询事件明细（脱敏）",
    "analytics:pii": "查看明文用户标识 / 按用户查事件",
    "analytics:export": "导出事件 CSV",
    "analytics:rebuild": "重算聚合数据",
    "audit:read": "查看审计日志",
    "admin:manage": "管理员账号与角色",
}


def permissions_for_role(role: str) -> list[str]:
    return list(ROLE_PERMISSIONS.get(role, []))


def has_permission(role: str, *needed: str) -> bool:
    granted = ROLE_PERMISSIONS.get(role, [])
    if "*" in granted:
        return True
    return all(p in granted for p in needed)


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

    async def change_password(
        self, admin: AdminUser, old_password: str, new_password: str, ip: str | None = None
    ) -> dict:
        if not verify_password(old_password, admin.password_hash):
            raise AppError(ErrorCodes.ADMIN_INVALID_CREDENTIALS, "原密码不正确", status_code=400)
        if old_password == new_password:
            raise AppError(ErrorCodes.AUTH_INVALID, "新密码不能与原密码相同")
        admin.password_hash = hash_password(new_password)
        admin.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await write_audit(
            self.db,
            admin_id=admin.id,
            action="admin_password_changed",
            target_type="admin_user",
            target_id=str(admin.id),
            detail={"username": admin.username},
            ip=ip,
        )
        return {"changed": True}

    async def me(self, admin: AdminUser) -> dict:
        return {
            "id": admin.id,
            "username": admin.username,
            "display_name": admin.display_name,
            "role": admin.role,
            "role_label": ROLE_META.get(admin.role, {}).get("label", admin.role),
            "permissions": permissions_for_role(admin.role),
            "last_login_at": admin.last_login_at.isoformat() if admin.last_login_at else None,
        }
