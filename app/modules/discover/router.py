from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.modules.discover.schemas import SwipeRequest
from app.modules.discover.service import DiscoverService
from app.modules.match.service import MatchService
from app.shared.deps import get_current_user, get_db, get_request_id
from app.shared.response import ok

router = APIRouter(prefix="/api/v1", tags=["discover"])


@router.get("/discover/cards")
async def discover_cards(
    request: Request,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=30),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await DiscoverService(db).get_cards(user, cursor=cursor, limit=limit)
    return ok(data, request_id=get_request_id(request))


@router.post("/swipes")
async def create_swipe(
    body: SwipeRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await MatchService(db).swipe(
        user,
        body.target_user_id,
        body.action,
        body.idempotency_key,
    )
    return ok(data, request_id=get_request_id(request))


@router.get("/matches")
async def list_matches(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await MatchService(db).list_matches(user)
    return ok({"items": data}, request_id=get_request_id(request))


@router.delete("/matches/{match_id}")
async def unmatch(
    match_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from uuid import UUID

    data = await MatchService(db).unmatch(user, UUID(match_id))
    return ok(data, request_id=get_request_id(request))
