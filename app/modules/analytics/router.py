from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.modules.analytics.schemas import AnalyticsBatchIn
from app.modules.analytics.service import AnalyticsService
from app.shared.deps import get_db, get_optional_user, get_request_id
from app.shared.rate_limit import enforce_rate_limit
from app.shared.response import ok

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.post("/events")
async def ingest_events(
    body: AnalyticsBatchIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    request.state.rate_limit_user = body.events[0].anon_id
    await enforce_rate_limit(request, bucket="analytics", limit=60, window_seconds=60)
    client_ip = request.client.host if request.client else None
    data = await AnalyticsService(db).ingest(body, user=user, client_ip=client_ip)
    return ok(data, request_id=get_request_id(request))
