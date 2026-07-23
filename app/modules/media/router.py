from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.modules.media.schemas import MediaCompleteRequest, StsRequest
from app.modules.media.service import MediaService
from app.shared.deps import get_current_user, get_db, get_request_id
from app.shared.response import ok

router = APIRouter(prefix="/api/v1/media", tags=["media"])


@router.post("/sts")
async def create_sts(
    body: StsRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await MediaService(db).create_sts(user, body.media_type, body.content_type, body.ext)
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
    )
    return ok(data, request_id=get_request_id(request))
