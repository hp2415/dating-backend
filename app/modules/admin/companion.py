"""Admin companion / buddy read + review."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminUser, BuddyIntent, CompanionBooking, CompanionProfile
from app.modules.admin.deps import require_perm
from app.modules.companion.schemas import AdminCompanionReview
from app.modules.companion.service import CompanionServiceLayer
from app.shared.deps import get_db, get_request_id
from app.shared.errors import AppError
from app.shared.pagination import legacy_admin_page
from app.shared.response import ErrorCodes, ok

router = APIRouter(prefix="/admin/v1", tags=["admin-companion"])


@router.get("/companions")
async def admin_list_companions(
    request: Request,
    status: str | None = Query(default="pending"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("companion:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    filters = []
    if status:
        filters.append(CompanionProfile.status == status)
    count_q = select(func.count()).select_from(CompanionProfile)
    list_q = select(CompanionProfile).order_by(CompanionProfile.created_at.desc())
    for f in filters:
        count_q = count_q.where(f)
        list_q = list_q.where(f)
    total = int((await db.execute(count_q)).scalar_one())
    rows = list((await db.execute(list_q.limit(limit).offset(offset))).scalars().all())
    svc = CompanionServiceLayer(db)
    items = [await svc.profile_brief(p, include_private=True) for p in rows]
    return ok(legacy_admin_page(items, total=total, limit=limit, offset=offset), request_id=get_request_id(request))


@router.post("/companions/{user_id}/review")
async def admin_review_companion(
    user_id: UUID,
    body: AdminCompanionReview,
    request: Request,
    admin: AdminUser = Depends(require_perm("companion:review")),
    db: AsyncSession = Depends(get_db),
):
    if body.action not in ("approve", "reject"):
        raise AppError(ErrorCodes.COMPANION_INVALID, "action 须为 approve|reject")
    data = await CompanionServiceLayer(db).admin_review_companion(
        admin.id, user_id, approve=body.action == "approve", reason=body.reason
    )
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.get("/bookings")
async def admin_list_bookings(
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("companion:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    filters = []
    if status:
        filters.append(CompanionBooking.status == status)
    count_q = select(func.count()).select_from(CompanionBooking)
    list_q = select(CompanionBooking).order_by(CompanionBooking.created_at.desc())
    for f in filters:
        count_q = count_q.where(f)
        list_q = list_q.where(f)
    total = int((await db.execute(count_q)).scalar_one())
    rows = list((await db.execute(list_q.limit(limit).offset(offset))).scalars().all())
    svc = CompanionServiceLayer(db)
    items = [await svc.booking_brief(b) for b in rows]
    return ok(legacy_admin_page(items, total=total, limit=limit, offset=offset), request_id=get_request_id(request))


@router.get("/buddy-intents")
async def admin_list_intents(
    request: Request,
    active: bool | None = Query(default=True),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("companion:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    filters = []
    if active is not None:
        filters.append(BuddyIntent.active.is_(active))
    count_q = select(func.count()).select_from(BuddyIntent)
    list_q = select(BuddyIntent).order_by(BuddyIntent.updated_at.desc())
    for f in filters:
        count_q = count_q.where(f)
        list_q = list_q.where(f)
    total = int((await db.execute(count_q)).scalar_one())
    rows = list((await db.execute(list_q.limit(limit).offset(offset))).scalars().all())
    svc = CompanionServiceLayer(db)
    items = [{**svc.intent_brief(r), "user_id": str(r.user_id)} for r in rows]
    return ok(legacy_admin_page(items, total=total, limit=limit, offset=offset), request_id=get_request_id(request))
