"""Admin: role catalogue + admin account management (permission ``admin:manage``, superadmin only by default)."""

from __future__ import annotations

import re
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminUser
from app.modules.admin.audit import write_audit
from app.modules.admin.deps import get_current_admin, require_perm
from app.modules.admin.service import PERMISSION_LABELS, ROLE_META, ROLE_PERMISSIONS
from app.shared.deps import get_db, get_request_id
from app.shared.errors import AppError
from app.shared.passwords import hash_password
from app.shared.response import ErrorCodes, ok

router = APIRouter(prefix="/admin/v1", tags=["admin-accounts"])

_USERNAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]{2,31}$")


def _check_password(pw: str) -> None:
    if len(pw) < 10 or not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        raise AppError(ErrorCodes.AUTH_INVALID, "密码至少 10 位，且同时包含字母和数字")


def _brief(a: AdminUser) -> dict:
    meta = ROLE_META.get(a.role, {})
    return {
        "id": str(a.id), "username": a.username, "display_name": a.display_name, "role": a.role,
        "role_label": meta.get("label", a.role), "is_active": a.is_active,
        "last_login_at": a.last_login_at.isoformat() if a.last_login_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


class AdminCreate(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=10, max_length=72)
    display_name: str = Field(default="", max_length=64)
    role: str


class AdminUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=64)
    role: str | None = None
    is_active: bool | None = None
    new_password: str | None = Field(default=None, min_length=10, max_length=72)


@router.get("/roles")
async def roles(request: Request, admin: AdminUser = Depends(get_current_admin)):
    """Role catalogue with permission lists (any signed-in admin may read; it is documentation)."""
    _ = admin
    items = []
    for key, perms in ROLE_PERMISSIONS.items():
        meta = ROLE_META.get(key, {})
        items.append({"key": key, "label": meta.get("label", key), "desc": meta.get("desc", ""), "permissions": perms})
    return ok({"items": items, "permission_labels": PERMISSION_LABELS}, request_id=get_request_id(request))


@router.get("/admins")
async def list_admins(
    request: Request,
    admin: AdminUser = Depends(require_perm("admin:manage")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    rows = (await db.execute(select(AdminUser).order_by(AdminUser.created_at))).scalars().all()
    return ok({"items": [_brief(a) for a in rows], "total": len(rows)}, request_id=get_request_id(request))


@router.post("/admins")
async def create_admin(
    body: AdminCreate,
    request: Request,
    admin: AdminUser = Depends(require_perm("admin:manage")),
    db: AsyncSession = Depends(get_db),
):
    if not _USERNAME_RE.match(body.username):
        raise AppError(ErrorCodes.AUTH_INVALID, "用户名需以字母开头，3-32 位字母数字或 _.-")
    if body.role not in ROLE_PERMISSIONS:
        raise AppError(ErrorCodes.AUTH_INVALID, "未知角色")
    _check_password(body.password)
    exists = await db.scalar(select(func.count()).select_from(AdminUser).where(func.lower(AdminUser.username) == body.username.lower()))
    if exists:
        raise AppError(ErrorCodes.AUTH_INVALID, "用户名已存在", status_code=409)
    row = AdminUser(
        id=uuid4(), username=body.username, password_hash=hash_password(body.password),
        display_name=body.display_name or body.username, role=body.role, is_active=True,
    )
    db.add(row)
    await db.flush()
    write_audit(db, admin, action="admin_create", target_type="admin_user", target_id=str(row.id),
                detail={"username": row.username, "role": row.role},
                ip=request.client.host if request.client else None)
    await db.commit()
    return ok(_brief(row), request_id=get_request_id(request))


@router.put("/admins/{admin_id}")
async def update_admin(
    admin_id: UUID,
    body: AdminUpdate,
    request: Request,
    admin: AdminUser = Depends(require_perm("admin:manage")),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(AdminUser, admin_id)
    if row is None:
        raise AppError(ErrorCodes.AUTH_INVALID, "管理员不存在", status_code=404)
    changes: dict = {}
    demoting = (body.role is not None and body.role != "superadmin") or body.is_active is False
    if row.role == "superadmin" and demoting:
        remaining = await db.scalar(
            select(func.count()).select_from(AdminUser).where(
                AdminUser.role == "superadmin", AdminUser.is_active.is_(True), AdminUser.id != row.id
            )
        )
        if not remaining:
            raise AppError(ErrorCodes.AUTH_INVALID, "不能停用或降级最后一个超级管理员", status_code=409)
    if row.id == admin.id and (body.is_active is False or (body.role and body.role != row.role)):
        raise AppError(ErrorCodes.AUTH_INVALID, "不能停用自己或修改自己的角色", status_code=409)
    if body.role is not None:
        if body.role not in ROLE_PERMISSIONS:
            raise AppError(ErrorCodes.AUTH_INVALID, "未知角色")
        if body.role != row.role:
            changes["role"] = {"from": row.role, "to": body.role}
            row.role = body.role
    if body.display_name is not None:
        row.display_name = body.display_name
    if body.is_active is not None and body.is_active != row.is_active:
        changes["is_active"] = body.is_active
        row.is_active = body.is_active
    if body.new_password:
        _check_password(body.new_password)
        row.password_hash = hash_password(body.new_password)
        changes["password_reset"] = True
    await db.flush()
    write_audit(db, admin, action="admin_update", target_type="admin_user", target_id=str(row.id),
                detail={"username": row.username, **changes}, ip=request.client.host if request.client else None)
    await db.commit()
    return ok(_brief(row), request_id=get_request_id(request))
