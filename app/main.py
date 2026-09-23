from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.modules.activity.router import router as activity_router
from app.modules.analytics.router import router as analytics_router
from app.modules.admin.router import router as admin_router
from app.modules.admin.seed import ensure_default_admin
from app.modules.auth.router import router as auth_router
from app.modules.auth.sms_provider import sms_status
from app.modules.chat_gate.router import router as chat_router
from app.modules.community.router import me_router as community_me_router
from app.modules.community.router import router as community_router
from app.modules.discover.router import router as discover_router
from app.modules.discover.seed import ensure_demo_users
from app.modules.events.router import router as events_ops_router
from app.modules.commerce.router import internal_router as pay_internal_router
from app.modules.commerce.router import router as commerce_router
from app.modules.commerce.seed import ensure_membership_plans
from app.modules.admin.commerce import router as admin_commerce_router
from app.modules.admin.messaging import router as admin_messaging_router
from app.modules.admin.companion import router as admin_companion_router
from app.modules.admin.trust import router as admin_trust_router
from app.modules.admin.ops import router as admin_ops_router
from app.modules.admin.users import router as admin_users_router
from app.modules.companion.router import router as companion_router
from app.modules.trust.router import router as trust_router
from app.modules.ops.router import router as ops_router
from app.modules.ops.seed import ensure_default_taxonomies
from app.modules.media.router import me_router as media_me_router
from app.modules.media.router import router as media_router
from app.modules.media.storage import get_storage
from app.modules.messaging.router import router as messaging_router
from app.modules.recommend.router import router as recommend_router
from app.modules.safety.router import router as safety_router
from app.modules.user.router import router as user_router
from app.shared.config import settings
from app.shared.db import SessionLocal, engine
from app.shared.errors import AppError
from app.shared.middleware import RequestIdMiddleware
from app.shared.observability import capture_exception, configure_logging, init_sentry
from app.shared.redis_client import close_redis, get_redis
from app.shared.response import ErrorCodes, fail, ok

logger = logging.getLogger("dating-api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    init_sentry()
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    redis = get_redis()
    await redis.ping()
    if settings.storage_driver == "local":
        Path(settings.media_local_root).mkdir(parents=True, exist_ok=True)
    async with SessionLocal() as session:
        await ensure_default_admin(session)
        await ensure_demo_users(session)
        await ensure_membership_plans(session)
        await ensure_default_taxonomies(session)
    yield
    await close_redis()
    await engine.dispose()


_expose_docs = settings.app_env == "development"
app = FastAPI(
    title=settings.app_name,
    version="0.9.3",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
    docs_url="/docs" if _expose_docs else None,
    redoc_url="/redoc" if _expose_docs else None,
    openapi_url="/openapi.json" if _expose_docs else None,
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
app.include_router(analytics_router)
app.include_router(user_router)
app.include_router(media_router)
app.include_router(media_me_router)
app.include_router(discover_router)
app.include_router(safety_router)
app.include_router(recommend_router)
app.include_router(activity_router)
app.include_router(community_router)
app.include_router(community_me_router)
app.include_router(chat_router)
app.include_router(messaging_router)
app.include_router(companion_router)
app.include_router(trust_router)
app.include_router(ops_router)
app.include_router(commerce_router)
app.include_router(pay_internal_router)
app.include_router(admin_router)
app.include_router(admin_commerce_router)
app.include_router(admin_messaging_router)
app.include_router(admin_companion_router)
app.include_router(admin_trust_router)
app.include_router(admin_ops_router)
app.include_router(admin_users_router)
app.include_router(events_ops_router)

if settings.storage_driver == "local":
    Path(settings.media_local_root).mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=settings.media_local_root), name="media")


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


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    logger.exception("unhandled error request_id=%s path=%s", request_id, request.url.path)
    capture_exception(exc)
    return ORJSONResponse(
        status_code=500,
        content=fail(
            ErrorCodes.SYSTEM_ERROR,
            "服务器内部错误",
            request_id=request_id,
        ),
    )


@app.get("/health")
async def health(request: Request):
    redis = get_redis()
    pg_ok = False
    redis_ok = False
    worker_ok = False
    postgis_ok = False
    pg_error = None
    redis_error = None

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            ext = await conn.execute(
                text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'postgis')")
            )
            postgis_ok = bool(ext.scalar())
        pg_ok = True
    except Exception as exc:  # noqa: BLE001
        pg_error = str(exc)

    try:
        redis_ok = bool(await redis.ping())
        worker_ok = bool(await redis.get("worker:heartbeat") or await redis.get("worker:arq"))
    except Exception as exc:  # noqa: BLE001
        redis_error = str(exc)

    storage = get_storage()
    status = "ok" if pg_ok and redis_ok else "degraded"
    return ok(
        {
            "app": settings.app_name,
            "env": settings.app_env,
            "version": "0.9.2",
            "postgres": {"ok": pg_ok, "error": pg_error, "postgis": postgis_ok},
            "redis": {"ok": redis_ok, "error": redis_error},
            "worker": {"ok": worker_ok},
            "payment": {
                "provider": settings.payment_provider,
                "stub_auto_complete": settings.payment_stub_auto_complete,
            },
            "im": {"provider": settings.im_provider, "ready": settings.im_provider != "noop"},
            "sms": sms_status(),
            "storage": {
                "driver": settings.storage_driver,
                "provider": storage.name,
                "media_auto_approve": settings.media_auto_approve,
                "local_root": settings.media_local_root if settings.storage_driver == "local" else None,
                "oss_endpoint": settings.oss_endpoint if settings.storage_driver == "oss" else None,
                "oss_bucket": settings.oss_bucket if settings.storage_driver == "oss" else None,
            },
        },
        message=status,
        request_id=getattr(request.state, "request_id", None),
    )


@app.get("/api/v1/ping")
async def ping(request: Request):
    return ok({"pong": True}, request_id=getattr(request.state, "request_id", None))
