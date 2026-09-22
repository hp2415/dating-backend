from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminAuditLog, AdminRole, AdminUser
from app.shared.config import settings
from app.shared.passwords import hash_password


async def ensure_default_admin(db: AsyncSession) -> None:
    """Bootstrap demo admin accounts (idempotent; does not reset existing passwords)."""
    await ensure_demo_admin_accounts(db)


async def ensure_demo_admin_accounts(db: AsyncSession) -> None:
    """Ensure admin / auditor / finance exist even when admin_users is not empty.

    Passwords always come from settings.admin_default_password. Existing rows are left alone.
    """
    specs: list[tuple[str, str, str]] = [
        (settings.admin_default_username, AdminRole.SUPERADMIN.value, "系统管理员"),
        ("auditor", AdminRole.AUDITOR.value, "审核员"),
        ("finance", AdminRole.FINANCE.value, "财务"),
    ]
    created: list[str] = []
    for username, role, display_name in specs:
        result = await db.execute(select(AdminUser).where(AdminUser.username == username))
        if result.scalar_one_or_none() is not None:
            continue
        admin = AdminUser(
            id=uuid4(),
            username=username,
            password_hash=hash_password(settings.admin_default_password),
            display_name=display_name,
            role=role,
            is_active=True,
            last_login_at=None,
        )
        db.add(admin)
        await db.flush()
        db.add(
            AdminAuditLog(
                id=uuid4(),
                admin_id=admin.id,
                action="seed_demo_admin",
                target_type="admin_user",
                target_id=str(admin.id),
                detail={"username": admin.username, "role": role},
                ip=None,
            )
        )
        created.append(username)
    if created:
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
