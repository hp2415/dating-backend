import logging
import time
import uuid
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("dating.access")
_SKIP_PATHS = {"/health"}


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            if request.url.path not in _SKIP_PATHS:
                _log_access(request, request_id, 500, started)
            raise
        response.headers["X-Request-Id"] = request_id
        if request.url.path not in _SKIP_PATHS:
            _log_access(request, request_id, response.status_code, started)
        return response


def _log_access(request: Request, request_id: str, status: int, started: float) -> None:
    duration_ms = int((time.perf_counter() - started) * 1000)
    forwarded = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else ""
    )
    if status >= 500:
        level = logging.ERROR
    elif status >= 400:
        level = logging.WARNING
    else:
        level = logging.INFO
    logger.log(
        level,
        "%s %s %s %dms",
        request.method,
        request.url.path,
        status,
        duration_ms,
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": status,
            "duration_ms": duration_ms,
            "client_ip": client_ip,
        },
    )
