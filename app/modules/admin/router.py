from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminUser
from app.modules.admin.deps import get_current_admin
from app.modules.admin.activity import ActivityAdminService, ReviewActivityRequest
from app.modules.admin.community import CommunityAdminService, ReviewPostRequest
from app.modules.admin.moderation import (
    ModerationService,
    ResolveReportRequest,
    ReviewMediaRequest,
)
from app.modules.admin.schemas import AdminLoginRequest
from app.modules.admin.service import AdminAuthService
from app.shared.deps import get_db, get_request_id
from app.shared.response import ok

router = APIRouter(prefix="/admin/v1", tags=["admin"])


@router.post("/auth/login")
async def admin_login(
    body: AdminLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip = request.client.host if request.client else None
    data = await AdminAuthService(db).login(body.username, body.password, ip=ip)
    return ok(data, request_id=get_request_id(request))


@router.get("/auth/me")
async def admin_me(
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    data = await AdminAuthService(db).me(admin)
    return ok(data, request_id=get_request_id(request))


@router.get("/dashboard/summary")
async def dashboard_summary(
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    data = await ModerationService(db).dashboard_summary(admin)
    return ok(data, request_id=get_request_id(request))


@router.get("/reports")
async def list_reports(
    request: Request,
    status: str | None = Query(default="pending"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    data = await ModerationService(db).list_reports(status, limit, offset)
    return ok(data, request_id=get_request_id(request))


@router.post("/reports/{report_id}/resolve")
async def resolve_report(
    report_id: UUID,
    body: ResolveReportRequest,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    data = await ModerationService(db).resolve_report(admin, report_id, body)
    return ok(data, request_id=get_request_id(request))


@router.get("/media")
async def list_media(
    request: Request,
    audit_status: str | None = Query(default="pending"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    data = await ModerationService(db).list_media(audit_status, limit, offset)
    return ok(data, request_id=get_request_id(request))


@router.post("/media/{media_id}/review")
async def review_media(
    media_id: UUID,
    body: ReviewMediaRequest,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    data = await ModerationService(db).review_media(admin, media_id, body)
    return ok(data, request_id=get_request_id(request))


@router.get("/community/posts")
async def list_community_posts(
    request: Request,
    status: str | None = Query(default="pending"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    data = await CommunityAdminService(db).list_posts(status, limit, offset)
    return ok(data, request_id=get_request_id(request))


@router.post("/community/posts/{post_id}/review")
async def review_community_post(
    post_id: UUID,
    body: ReviewPostRequest,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    data = await CommunityAdminService(db).review_post(admin, post_id, body)
    return ok(data, request_id=get_request_id(request))


@router.get("/activities")
async def list_activities_admin(
    request: Request,
    status: str | None = Query(default="pending"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    data = await ActivityAdminService(db).list_activities(status, limit, offset)
    return ok(data, request_id=get_request_id(request))


@router.post("/activities/{activity_id}/review")
async def review_activity(
    activity_id: UUID,
    body: ReviewActivityRequest,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    data = await ActivityAdminService(db).review(admin, activity_id, body)
    return ok(data, request_id=get_request_id(request))
