"""Redis token-bucket rate limit dependency."""

from __future__ import annotations

from fastapi import Request

from app.shared.config import settings
from app.shared.errors import AppError
from app.shared.redis_client import get_redis
from app.shared.response import ErrorCodes


async def enforce_rate_limit(
    request: Request,
    *,
    bucket: str,
    limit: int | None = None,
    window_seconds: int | None = None,
) -> None:
    """Raise AppError when the bucket exceeds limit in the sliding window."""
    max_hits = limit if limit is not None else settings.rate_limit_per_minute
    window = window_seconds if window_seconds is not None else 60
    if max_hits <= 0:
        return

    client_host = request.client.host if request.client else "unknown"
    user_key = getattr(request.state, "rate_limit_user", None) or client_host
    key = f"rl:{bucket}:{user_key}"

    redis = get_redis()
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window)
    if count > max_hits:
        raise AppError(
            ErrorCodes.AUTH_RATE_LIMIT,
            "请求过于频繁，请稍后再试",
            status_code=429,
        )
