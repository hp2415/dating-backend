from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.modules.recommend.service import EngagementRequest, RecommendService
from app.shared.deps import get_current_user, get_db, get_request_id
from app.shared.response import ok

router = APIRouter(tags=["recommend"])


@router.get("/api/v1/activities/browse")
async def browse_activities(
    request: Request,
    city: str | None = Query(default=None),
    category: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await RecommendService(db).browse_activities(
        user, city=city, category=category, limit=limit
    )
    return ok(data, request_id=get_request_id(request))


@router.post("/api/v1/engagement/activities")
async def track_activity_engagement(
    body: EngagementRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await RecommendService(db).track_engagement(user, body)
    return ok(data, request_id=get_request_id(request))


@router.get("/api/v1/buddies/recommend")
async def recommend_buddies(
    request: Request,
    limit: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await RecommendService(db).recommend_buddies(user, limit=limit)
    return ok(data, request_id=get_request_id(request))
