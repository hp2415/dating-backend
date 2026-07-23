from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminAuditLog, AdminRole, AdminUser
from app.shared.config import settings
from app.shared.passwords import hash_password


async def ensure_default_admin(db: AsyncSession) -> None:
    """Bootstrap a default admin account when table is empty (dev/first run)."""
    count = await db.scalar(select(func.count()).select_from(AdminUser))
    if count and count > 0:
        return

    admin = AdminUser(
        id=uuid4(),
        username=settings.admin_default_username,
        password_hash=hash_password(settings.admin_default_password),
        display_name="系统管理员",
        role=AdminRole.SUPERADMIN.value,
        is_active=True,
        last_login_at=None,
    )
    db.add(admin)
    await db.flush()
    db.add(
        AdminAuditLog(
            id=uuid4(),
            admin_id=admin.id,
            action="seed_default_admin",
            target_type="admin_user",
            target_id=str(admin.id),
            detail={"username": admin.username},
            ip=None,
        )
    )
    await db.commit()


async def write_audit(
    db: AsyncSession,
    *,
    admin_id: UUID | None,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    detail: dict | None = None,
    ip: str | None = None,
) -> None:
    db.add(
        AdminAuditLog(
            id=uuid4(),
            admin_id=admin_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail or {},
            ip=ip,
            created_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()
