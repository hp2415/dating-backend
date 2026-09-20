"""Admin user directory — list / detail / related slices / force-logout / reset-avatar."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Activity,
    ActivityParticipant,
    AdminAuditLog,
    AdminUser,
    Friendship,
    Order,
    RefreshToken,
    Sanction,
    User,
    UserProfile,
    WalletAccount,
)
from app.models.trust import TrustEvent, TrustScore
from app.modules.admin.deps import require_perm
from app.shared.deps import get_db, get_request_id
from app.shared.errors import AppError
from app.shared.pagination import legacy_admin_page
from app.shared.response import ErrorCodes, ok

router = APIRouter(prefix="/admin/v1", tags=["admin-users"])


def _mask_phone(phone: str) -> str:
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if len(digits) < 7:
        return "***"
    return f"{digits[:3]}****{digits[-4:]}"


def _user_brief(user: User, *, reveal_phone: bool = False) -> dict:
    profile = user.profile
    return {
        "id": str(user.id),
        "public_uid": user.public_uid,
        "phone_masked": _mask_phone(user.phone),
        "phone": user.phone if reveal_phone else None,
        "status": user.status,
        "discoverable": user.discoverable,
        "profile_completed": user.profile_completed,
        "display_name": (profile.display_name if profile else None) or "",
        "city": (profile.city if profile else None) or "",
        "gender": (profile.gender if profile else None) or "unknown",
        "bio": (profile.bio if profile else None) or "",
        "tags": list(profile.tags) if profile and profile.tags else [],
        "completion_score": profile.completion_score if profile else 0,
        "avatar_media_id": str(profile.avatar_media_id) if profile and profile.avatar_media_id else None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_active_at": user.last_active_at.isoformat() if user.last_active_at else None,
    }


async def _load_user(db: AsyncSession, user_id: UUID) -> User:
    result = await db.execute(
        select(User).options(selectinload(User.profile)).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise AppError(ErrorCodes.USER_NOT_FOUND, "用户不存在", status_code=404)
    return user


async def _audit(
    db: AsyncSession,
    *,
    admin: AdminUser,
    action: str,
    target_id: str,
    detail: dict | None = None,
    ip: str | None = None,
) -> None:
    db.add(
        AdminAuditLog(
            id=uuid4(),
            admin_id=admin.id,
            action=action,
            target_type="user",
            target_id=target_id,
            detail=detail or {},
            ip=ip,
        )
    )


@router.get("/users")
async def admin_list_users(
    request: Request,
    q: str | None = Query(default=None, description="手机号 / UID / 昵称"),
    status: str | None = Query(default=None),
    city: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("user:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    from sqlalchemy import func

    filters = []
    needs_profile = bool((q and q.strip()) or city)
    if status:
        filters.append(User.status == status)

    base = select(User.id)
    if needs_profile:
        base = base.outerjoin(UserProfile, UserProfile.user_id == User.id)
    if city:
        filters.append(UserProfile.city.ilike(f"%{city}%"))
    if q and q.strip():
        needle = q.strip()
        filters.append(
            or_(
                User.phone.contains(needle),
                User.public_uid == needle,
                UserProfile.display_name.ilike(f"%{needle}%"),
            )
        )
    if filters:
        base = base.where(*filters)

    total = int(await db.scalar(select(func.count()).select_from(base.subquery())) or 0)

    stmt = select(User).options(selectinload(User.profile)).order_by(User.created_at.desc())
    if needs_profile:
        stmt = stmt.outerjoin(UserProfile, UserProfile.user_id == User.id)
    if filters:
        stmt = stmt.where(*filters)
    result = await db.execute(stmt.offset(offset).limit(limit))
    users = list(result.scalars().unique().all())
    items = [_user_brief(u) for u in users]
    return ok(legacy_admin_page(items, total=total, limit=limit, offset=offset), request_id=get_request_id(request))


@router.get("/users/{user_id}")
async def admin_get_user(
    user_id: UUID,
    request: Request,
    admin: AdminUser = Depends(require_perm("user:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    user = await _load_user(db, user_id)
    wallet = (
        await db.execute(select(WalletAccount).where(WalletAccount.user_id == user_id))
    ).scalar_one_or_none()
    trust = (
        await db.execute(select(TrustScore).where(TrustScore.user_id == user_id))
    ).scalar_one_or_none()
    data = _user_brief(user)
    data["wallet_balance_cents"] = wallet.balance_cents if wallet else 0
    data["trust_score"] = float(trust.score) if trust else None
    data["trust_level"] = trust.level if trust else None
    return ok(data, request_id=get_request_id(request))


@router.get("/users/{user_id}/phone")
async def admin_reveal_phone(
    user_id: UUID,
    request: Request,
    admin: AdminUser = Depends(require_perm("user:write")),
    db: AsyncSession = Depends(get_db),
):
    user = await _load_user(db, user_id)
    await _audit(
        db,
        admin=admin,
        action="reveal_phone",
        target_id=str(user_id),
        ip=request.client.host if request.client else None,
    )
    await db.commit()
    return ok({"phone": user.phone, "phone_masked": _mask_phone(user.phone)}, request_id=get_request_id(request))


@router.get("/users/{user_id}/activities")
async def admin_user_activities(
    user_id: UUID,
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("user:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    await _load_user(db, user_id)
    hosted = (
        await db.execute(
            select(Activity)
            .where(Activity.host_id == user_id)
            .order_by(Activity.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    joined_ids = (
        await db.execute(
            select(ActivityParticipant.activity_id).where(ActivityParticipant.user_id == user_id)
        )
    ).scalars().all()
    joined = []
    if joined_ids:
        joined = list(
            (
                await db.execute(
                    select(Activity)
                    .where(Activity.id.in_(joined_ids))
                    .order_by(Activity.created_at.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
    def act_brief(a: Activity, role: str) -> dict:
        return {
            "id": str(a.id),
            "title": a.title,
            "status": a.status,
            "city": a.city,
            "role": role,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }

    items = [act_brief(a, "host") for a in hosted] + [
        act_brief(a, "member") for a in joined if a.host_id != user_id
    ]
    return ok({"items": items, "total": len(items)}, request_id=get_request_id(request))


@router.get("/users/{user_id}/orders")
async def admin_user_orders(
    user_id: UUID,
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("user:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    await _load_user(db, user_id)
    rows = (
        await db.execute(
            select(Order)
            .where(Order.user_id == user_id)
            .order_by(Order.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    items = [
        {
            "id": str(o.id),
            "order_no": o.order_no,
            "kind": o.kind,
            "subject_title": o.subject_title,
            "payable_cents": o.payable_cents,
            "status": o.status,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        }
        for o in rows
    ]
    return ok({"items": items, "total": len(items)}, request_id=get_request_id(request))


@router.get("/users/{user_id}/social")
async def admin_user_social(
    user_id: UUID,
    request: Request,
    admin: AdminUser = Depends(require_perm("user:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    await _load_user(db, user_id)
    friends = (
        await db.execute(select(Friendship).where(Friendship.user_id == user_id).limit(50))
    ).scalars().all()
    return ok(
        {
            "friend_count": len(friends),
            "friends": [
                {
                    "id": str(f.id),
                    "friend_id": str(f.friend_id),
                    "status": f.status,
                    "remark": f.remark,
                }
                for f in friends
            ],
        },
        request_id=get_request_id(request),
    )


@router.get("/users/{user_id}/trust-events")
async def admin_user_trust_events(
    user_id: UUID,
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("user:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    await _load_user(db, user_id)
    rows = (
        await db.execute(
            select(TrustEvent)
            .where(TrustEvent.subject_user_id == user_id)
            .order_by(TrustEvent.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    items = [
        {
            "id": str(e.id),
            "domain": e.domain,
            "name": e.name,
            "value": float(e.value),
            "note": e.note,
            "source": e.source,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in rows
    ]
    return ok({"items": items, "total": len(items)}, request_id=get_request_id(request))


@router.get("/users/{user_id}/sanctions")
async def admin_user_sanctions(
    user_id: UUID,
    request: Request,
    admin: AdminUser = Depends(require_perm("user:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    await _load_user(db, user_id)
    rows = (
        await db.execute(
            select(Sanction).where(Sanction.user_id == user_id).order_by(Sanction.created_at.desc()).limit(50)
        )
    ).scalars().all()
    items = [
        {
            "id": str(s.id),
            "kind": s.kind,
            "reason": s.reason,
            "scope": s.scope,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "expires_at": s.expires_at.isoformat() if s.expires_at else None,
            "revoked_at": s.revoked_at.isoformat() if s.revoked_at else None,
        }
        for s in rows
    ]
    return ok({"items": items, "total": len(items)}, request_id=get_request_id(request))


@router.post("/users/{user_id}/force-logout")
async def admin_force_logout(
    user_id: UUID,
    request: Request,
    admin: AdminUser = Depends(require_perm("user:write")),
    db: AsyncSession = Depends(get_db),
):
    await _load_user(db, user_id)
    await db.execute(
        update(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False)).values(revoked=True)
    )
    await _audit(
        db,
        admin=admin,
        action="force_logout",
        target_id=str(user_id),
        ip=request.client.host if request.client else None,
    )
    await db.commit()
    return ok({"ok": True}, request_id=get_request_id(request))


@router.post("/users/{user_id}/reset-avatar")
async def admin_reset_avatar(
    user_id: UUID,
    request: Request,
    admin: AdminUser = Depends(require_perm("user:write")),
    db: AsyncSession = Depends(get_db),
):
    user = await _load_user(db, user_id)
    if user.profile is not None:
        user.profile.avatar_media_id = None
    await _audit(
        db,
        admin=admin,
        action="reset_avatar",
        target_id=str(user_id),
        ip=request.client.host if request.client else None,
    )
    await db.commit()
    return ok({"ok": True}, request_id=get_request_id(request))
