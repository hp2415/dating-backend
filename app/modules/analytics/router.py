from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.modules.analytics.schemas import AnalyticsBatchIn
from app.modules.analytics.service import AnalyticsService, client_config
from app.shared.config import settings
from app.shared.deps import get_db, get_optional_user, get_request_id
from app.shared.errors import AppError
from app.shared.rate_limit import enforce_rate_limit
from app.shared.response import ErrorCodes, ok

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/config")
async def analytics_config(request: Request):
    """Public: kill switch, sampling and batching knobs for the SDK."""
    return ok(client_config(), request_id=get_request_id(request))


@router.post("/events")
async def ingest_events(
    body: AnalyticsBatchIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    if not settings.analytics_enabled:
        # Kill switch: acknowledge so clients drop their queue instead of retrying forever.
        return ok(
            {"accepted": 0, "duplicated": 0, "rejected": [], "sanitized_props": 0, "config": client_config()},
            request_id=get_request_id(request),
        )
    # Two buckets: per device (abuse of one install) and per IP (NAT-friendly ceiling).
    await enforce_rate_limit(request, bucket="analytics_ip", limit=settings.analytics_ingest_ip_per_minute, window_seconds=60)
    request.state.rate_limit_user = body.events[0].anon_id
    await enforce_rate_limit(request, bucket="analytics", limit=settings.analytics_ingest_per_minute, window_seconds=60)
    client_ip = request.client.host if request.client else None
    data = await AnalyticsService(db).ingest(body, user=user, client_ip=client_ip)
    return ok(data, request_id=get_request_id(request))


@router.delete("/me")
async def delete_my_analytics(
    request: Request,
    anon_id: str | None = Query(default=None, max_length=64),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    """Erase raw analytics for the signed-in user and/or this device — 注销 / 撤回授权.

    Works without a session too (a user can withdraw consent while logged out): the random per-install
    ``anon_id`` acts as the device secret.
    """
    if user is None and not anon_id:
        raise AppError(ErrorCodes.AUTH_INVALID, "缺少用户或设备标识")
    await enforce_rate_limit(request, bucket="analytics_ip", limit=settings.analytics_ingest_ip_per_minute, window_seconds=60)
    data = await AnalyticsService(db).delete_my_data(user_id=user.id if user else None, anon_id=anon_id)
    return ok(data, request_id=get_request_id(request))
