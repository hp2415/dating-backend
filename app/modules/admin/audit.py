"""Shared helper to write an admin audit-log row."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminAuditLog, AdminUser


def write_audit(
    db: AsyncSession,
    admin: AdminUser,
    *,
    action: str,
    target_type: str,
    target_id: str | None = None,
    detail: dict | None = None,
    ip: str | None = None,
) -> None:
    db.add(
        AdminAuditLog(
            id=uuid4(),
            admin_id=admin.id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail or {},
            ip=ip,
        )
    )
