from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.modules.media.schemas import MediaCompleteRequest, StsRequest
from app.modules.media.service import MediaService
from app.shared.deps import get_current_user, get_db, get_request_id
from app.shared.pagination import page_offset
from app.shared.response import ok

router = APIRouter(prefix="/api/v1/media", tags=["media"])


def _request_base(request: Request) -> str:
    """Prefer X-Forwarded-* when behind nginx; else scheme+host."""
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if host:
        return f"{proto}://{host}"
    return str(request.base_url).rstrip("/")


@router.post("/sts")
async def create_sts(
    body: StsRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await MediaService(db).create_sts(
        user,
        body.media_type,
        body.content_type,
        body.ext,
        request_base=_request_base(request),
    )
    return ok(data, request_id=get_request_id(request))


@router.put("/upload")
async def upload_object(
    request: Request,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Token-authenticated PUT. No Bearer header — used by bare OkHttp upload."""
    _ = db
    body = await request.body()
    data = await MediaService(db).save_upload(token, body)
    return ok(data, request_id=get_request_id(request))


@router.post("/complete")
async def media_complete(
    body: MediaCompleteRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    meta = {}
    if body.width:
        meta["width"] = body.width
    if body.height:
        meta["height"] = body.height
    data = await MediaService(db).complete(
        user,
        body.object_key,
        body.media_type,
        body.set_as_avatar,
        meta,
        request_base=_request_base(request),
    )
    return ok(data, request_id=get_request_id(request))


# Album / media library (mounted under /api/v1 so paths are /api/v1/me/media)
me_router = APIRouter(prefix="/api/v1", tags=["media"])


@me_router.get("/me/media")
async def list_my_media(
    request: Request,
    media_type: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await MediaService(db).list_mine(
        user, media_type=media_type, limit=limit, offset=offset
    )
    return ok(
        page_offset(items, total=total, limit=limit, offset=offset),
        request_id=get_request_id(request),
    )


@me_router.delete("/me/media/{media_id}")
async def delete_my_media(
    media_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await MediaService(db).soft_delete(user, media_id)
    return ok(data, request_id=get_request_id(request))
