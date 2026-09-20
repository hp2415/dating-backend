from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.modules.activity.service import (
    ActivityDetailsRequest,
    ActivityService,
    CancelActivityRequest,
    CreateActivityRequest,
    CreateCommentRequest,
    UpdateActivityRequest,
)
from app.shared.deps import get_current_user, get_db, get_request_id
from app.shared.response import ok

router = APIRouter(prefix="/api/v1/activities", tags=["activities"])


@router.post("")
async def create_activity(
    body: CreateActivityRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await ActivityService(db).create(user, body)
    return ok(data, request_id=get_request_id(request))


@router.get("")
async def list_activities(
    request: Request,
    city: str | None = Query(default=None),
    category: str | None = Query(default=None),
    mine: str | None = Query(default=None, description="hosted|joined"),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await ActivityService(db).list_feed(
        user, city=city, category=category, mine=mine, limit=limit, offset=offset
    )
    return ok(data, request_id=get_request_id(request))


@router.get("/search")
async def search_activities(
    request: Request,
    q: str | None = Query(default=None),
    city: str | None = Query(default=None),
    category: str | None = Query(default=None),
    fee_type: str | None = Query(default=None),
    free_only: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await ActivityService(db).search(
        user,
        q=q,
        city=city,
        category=category,
        fee_type=fee_type,
        free_only=free_only,
        limit=limit,
        offset=offset,
    )
    return ok(data, request_id=get_request_id(request))


@router.get("/{activity_id}")
async def get_activity(
    activity_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await ActivityService(db).get_detail(user, activity_id)
    return ok(data, request_id=get_request_id(request))


@router.put("/{activity_id}")
async def update_activity(
    activity_id: UUID,
    body: UpdateActivityRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await ActivityService(db).update(user, activity_id, body)
    return ok(data, request_id=get_request_id(request))


@router.post("/{activity_id}/cancel")
async def cancel_activity(
    activity_id: UUID,
    request: Request,
    body: CancelActivityRequest | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await ActivityService(db).cancel(user, activity_id, body or CancelActivityRequest())
    return ok(data, request_id=get_request_id(request))


@router.get("/{activity_id}/details")
async def get_activity_details(
    activity_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await ActivityService(db).get_details(user, activity_id)
    return ok(data, request_id=get_request_id(request))


@router.put("/{activity_id}/details")
async def put_activity_details(
    activity_id: UUID,
    body: ActivityDetailsRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await ActivityService(db).upsert_details(user, activity_id, body)
    return ok(data, request_id=get_request_id(request))


@router.post("/{activity_id}/favorite")
async def favorite_activity(
    activity_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await ActivityService(db).favorite(user, activity_id)
    return ok(data, request_id=get_request_id(request))


@router.delete("/{activity_id}/favorite")
async def unfavorite_activity(
    activity_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await ActivityService(db).unfavorite(user, activity_id)
    return ok(data, request_id=get_request_id(request))


@router.post("/{activity_id}/join")
async def join_activity(
    activity_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await ActivityService(db).join(user, activity_id)
    return ok(data, request_id=get_request_id(request))


@router.delete("/{activity_id}/join")
async def quit_activity(
    activity_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await ActivityService(db).quit(user, activity_id)
    return ok(data, request_id=get_request_id(request))


@router.get("/{activity_id}/members")
async def list_members(
    activity_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await ActivityService(db).list_members(user, activity_id)
    return ok(data, request_id=get_request_id(request))


@router.post("/{activity_id}/like")
async def like_activity(
    activity_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await ActivityService(db).like(user, activity_id)
    return ok(data, request_id=get_request_id(request))


@router.delete("/{activity_id}/like")
async def unlike_activity(
    activity_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await ActivityService(db).unlike(user, activity_id)
    return ok(data, request_id=get_request_id(request))


@router.get("/{activity_id}/comments")
async def list_comments(
    activity_id: UUID,
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await ActivityService(db).list_comments(user, activity_id, limit, offset)
    return ok(data, request_id=get_request_id(request))


@router.post("/{activity_id}/comments")
async def add_comment(
    activity_id: UUID,
    body: CreateCommentRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await ActivityService(db).add_comment(user, activity_id, body)
    return ok(data, request_id=get_request_id(request))
