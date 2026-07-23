from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from sqlalchemy import text

from app.modules.activity.router import router as activity_router
from app.modules.admin.router import router as admin_router
from app.modules.admin.seed import ensure_default_admin
from app.modules.auth.router import router as auth_router
from app.modules.chat_gate.router import router as chat_router
from app.modules.community.router import router as community_router
from app.modules.discover.router import router as discover_router
from app.modules.discover.seed import ensure_demo_users
from app.modules.media.router import router as media_router
from app.modules.safety.router import router as safety_router
from app.modules.user.router import router as user_router
from app.shared.config import settings
from app.shared.db import SessionLocal, engine
from app.shared.errors import AppError
from app.shared.middleware import RequestIdMiddleware
from app.shared.redis_client import close_redis, get_redis
from app.shared.response import ErrorCodes, fail, ok


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    redis = get_redis()
    await redis.ping()
    async with SessionLocal() as session:
        await ensure_default_admin(session)
        await ensure_demo_users(session)
    yield
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)

origins = [o.strip() for o in settings.admin_cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIdMiddleware)

app.include_router(auth_router)
app.include_router(user_router)
app.include_router(media_router)
app.include_router(discover_router)
app.include_router(safety_router)
app.include_router(activity_router)
app.include_router(community_router)
app.include_router(chat_router)
app.include_router(admin_router)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    request_id = getattr(request.state, "request_id", None)
    return ORJSONResponse(
        status_code=exc.status_code,
        content=fail(exc.code, exc.message, request_id=request_id),
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", None)
    return ORJSONResponse(
        status_code=422,
        content=fail(
            ErrorCodes.VALIDATION_ERROR,
            "参数校验失败",
            data=exc.errors(),
            request_id=request_id,
        ),
    )


@app.get("/health")
async def health(request: Request):
    redis = get_redis()
    pg_ok = False
    redis_ok = False
    pg_error = None
    redis_error = None

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        pg_ok = True
    except Exception as exc:  # noqa: BLE001
        pg_error = str(exc)

    try:
        redis_ok = bool(await redis.ping())
    except Exception as exc:  # noqa: BLE001
        redis_error = str(exc)

    status = "ok" if pg_ok and redis_ok else "degraded"
    return ok(
        {
            "app": settings.app_name,
            "env": settings.app_env,
            "postgres": {"ok": pg_ok, "error": pg_error},
            "redis": {"ok": redis_ok, "error": redis_error},
            "oss_endpoint": settings.oss_endpoint,
            "oss_bucket": settings.oss_bucket,
        },
        message=status,
        request_id=getattr(request.state, "request_id", None),
    )


@app.get("/api/v1/ping")
async def ping(request: Request):
    return ok({"pong": True}, request_id=getattr(request.state, "request_id", None))
