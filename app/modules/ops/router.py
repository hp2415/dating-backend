"""Client ops / config APIs."""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.modules.ops.schemas import FeedbackCreate, NotificationRead, PushTokenRegister
from app.modules.ops.service import OpsService
from app.shared.deps import get_current_user, get_db, get_request_id
from app.shared.pagination import page_offset
from app.shared.response import ok

router = APIRouter(tags=["ops"])


@router.get("/api/v1/taxonomies")
async def list_taxonomies(
    request: Request,
    kind: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _ = user
    items = await OpsService(db).list_taxonomies(kind=kind, enabled_only=True)
    return ok({"items": items}, request_id=get_request_id(request))


@router.get("/api/v1/discover/shelves")
async def list_discover_shelves(
    request: Request,
    city: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _ = user
    items = await OpsService(db).list_active_shelves(city=city)
    return ok({"items": items}, request_id=get_request_id(request))


@router.post("/api/v1/me/push-token")
async def register_push_token(
    body: PushTokenRegister,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await OpsService(db).register_push_token(user, body)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.get("/api/v1/notifications")
async def list_notifications(
    request: Request,
    unread_only: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await OpsService(db).list_notifications(
        user.id, limit=limit, offset=offset, unread_only=unread_only
    )
    return ok(
        page_offset(items, total=total, limit=limit, offset=offset),
        request_id=get_request_id(request),
    )


@router.post("/api/v1/notifications/read")
async def mark_notifications_read(
    body: NotificationRead,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await OpsService(db).mark_notifications_read(
        user.id, ids=body.ids, mark_all=body.all
    )
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.get("/api/v1/announcements")
async def list_announcements(
    request: Request,
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _ = user
    items, total = await OpsService(db).list_announcements(
        published_only=True, limit=limit, offset=offset
    )
    return ok(
        page_offset(items, total=total, limit=limit, offset=offset),
        request_id=get_request_id(request),
    )


@router.post("/api/v1/feedbacks")
async def create_feedback(
    body: FeedbackCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await OpsService(db).create_feedback(user, body)
    await db.commit()
    return ok(data, request_id=get_request_id(request))
