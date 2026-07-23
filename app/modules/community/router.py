from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.modules.community.service import (
    CommunityService,
    CreateCommentRequest,
    CreatePostRequest,
)
from app.shared.deps import get_current_user, get_db, get_request_id
from app.shared.response import ok

router = APIRouter(prefix="/api/v1/community", tags=["community"])


@router.post("/posts")
async def create_post(
    body: CreatePostRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await CommunityService(db).create_post(user, body)
    return ok(data, request_id=get_request_id(request))


@router.get("/posts")
async def list_posts(
    request: Request,
    mine: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = CommunityService(db)
    data = await (svc.list_mine(user, limit, offset) if mine else svc.list_feed(user, limit, offset))
    return ok(data, request_id=get_request_id(request))


@router.get("/posts/{post_id}")
async def get_post(
    post_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await CommunityService(db).get_post(user, post_id)
    return ok(data, request_id=get_request_id(request))


@router.delete("/posts/{post_id}")
async def delete_post(
    post_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await CommunityService(db).delete_post(user, post_id)
    return ok(data, request_id=get_request_id(request))


@router.post("/posts/{post_id}/like")
async def like_post(
    post_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await CommunityService(db).like(user, post_id)
    return ok(data, request_id=get_request_id(request))


@router.delete("/posts/{post_id}/like")
async def unlike_post(
    post_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await CommunityService(db).unlike(user, post_id)
    return ok(data, request_id=get_request_id(request))


@router.get("/posts/{post_id}/comments")
async def list_comments(
    post_id: UUID,
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await CommunityService(db).list_comments(user, post_id, limit, offset)
    return ok(data, request_id=get_request_id(request))


@router.post("/posts/{post_id}/comments")
async def add_comment(
    post_id: UUID,
    body: CreateCommentRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await CommunityService(db).add_comment(user, post_id, body)
    return ok(data, request_id=get_request_id(request))
