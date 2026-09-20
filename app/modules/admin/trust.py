"""Admin trust / verification / sanctions / moderation."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminUser
from app.modules.admin.deps import require_perm
from app.modules.trust.schemas import (
    AdminModerationReview,
    AdminSanctionCreate,
    AdminSanctionRevoke,
    AdminTrustAdjust,
    AdminVerificationReview,
    SensitiveWordUpsert,
)
from app.modules.trust.service import TrustService
from app.shared.deps import get_db, get_request_id
from app.shared.errors import AppError
from app.shared.pagination import legacy_admin_page
from app.shared.response import ErrorCodes, ok

router = APIRouter(prefix="/admin/v1", tags=["admin-trust"])


@router.get("/trust/scores")
async def admin_list_scores(
    request: Request,
    level: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("trust:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    items, total = await TrustService(db).list_scores(level=level, limit=limit, offset=offset)
    return ok(legacy_admin_page(items, total=total, limit=limit, offset=offset), request_id=get_request_id(request))


@router.get("/trust/events")
async def admin_list_events(
    request: Request,
    subject_user_id: UUID | None = Query(default=None),
    domain: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("trust:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    items, total = await TrustService(db).list_events(
        subject_user_id=subject_user_id, domain=domain, limit=limit, offset=offset
    )
    return ok(legacy_admin_page(items, total=total, limit=limit, offset=offset), request_id=get_request_id(request))


@router.post("/trust/adjust")
async def admin_trust_adjust(
    body: AdminTrustAdjust,
    request: Request,
    admin: AdminUser = Depends(require_perm("trust:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await TrustService(db).admin_adjust(admin, body)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.get("/verifications")
async def admin_list_verifications(
    request: Request,
    status: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("verification:review")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    items, total = await TrustService(db).list_verifications(
        status=status, kind=kind, limit=limit, offset=offset
    )
    return ok(legacy_admin_page(items, total=total, limit=limit, offset=offset), request_id=get_request_id(request))


@router.post("/verifications/{verification_id}/review")
async def admin_review_verification(
    verification_id: UUID,
    body: AdminVerificationReview,
    request: Request,
    admin: AdminUser = Depends(require_perm("verification:review")),
    db: AsyncSession = Depends(get_db),
):
    if body.action not in ("approve", "reject"):
        raise AppError(ErrorCodes.VERIFICATION_INVALID, "action 须为 approve|reject")
    data = await TrustService(db).admin_review_verification(
        admin, verification_id, approve=body.action == "approve", reason=body.reason
    )
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.get("/sanctions")
async def admin_list_sanctions(
    request: Request,
    user_id: UUID | None = Query(default=None),
    kind: str | None = Query(default=None),
    active_only: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("sanction:write")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    items, total = await TrustService(db).list_sanctions(
        user_id=user_id, kind=kind, active_only=active_only, limit=limit, offset=offset
    )
    return ok(legacy_admin_page(items, total=total, limit=limit, offset=offset), request_id=get_request_id(request))


@router.post("/sanctions")
async def admin_create_sanction(
    body: AdminSanctionCreate,
    request: Request,
    admin: AdminUser = Depends(require_perm("sanction:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await TrustService(db).admin_apply_sanction(admin, body)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/sanctions/{sanction_id}/revoke")
async def admin_revoke_sanction(
    sanction_id: UUID,
    body: AdminSanctionRevoke,
    request: Request,
    admin: AdminUser = Depends(require_perm("sanction:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await TrustService(db).admin_revoke_sanction(admin, sanction_id, reason=body.reason)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.get("/moderation-tasks")
async def admin_list_moderation_tasks(
    request: Request,
    status: str | None = Query(default=None),
    target_kind: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("moderation:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    items, total = await TrustService(db).list_moderation_tasks(
        status=status, target_kind=target_kind, limit=limit, offset=offset
    )
    return ok(legacy_admin_page(items, total=total, limit=limit, offset=offset), request_id=get_request_id(request))


@router.post("/moderation-tasks/{task_id}/claim")
async def admin_claim_moderation_task(
    task_id: UUID,
    request: Request,
    admin: AdminUser = Depends(require_perm("moderation:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await TrustService(db).claim_moderation_task(admin, task_id)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/moderation-tasks/{task_id}/review")
async def admin_review_moderation_task(
    task_id: UUID,
    body: AdminModerationReview,
    request: Request,
    admin: AdminUser = Depends(require_perm("moderation:write")),
    db: AsyncSession = Depends(get_db),
):
    if body.action not in ("approve", "reject"):
        raise AppError(ErrorCodes.TRUST_INVALID, "action 须为 approve|reject")
    data = await TrustService(db).review_moderation_task(
        admin,
        task_id,
        approve=body.action == "approve",
        reason_code=body.reason_code,
        admin_note=body.admin_note,
    )
    await db.commit()
    return ok(data, request_id=get_request_id(request))


MODERATION_REASON_CODES = [
    {"code": "spam", "label": "垃圾信息 / 广告引流"},
    {"code": "harassment", "label": "骚扰 / 人身攻击"},
    {"code": "inappropriate", "label": "不当内容"},
    {"code": "fake", "label": "虚假资料 / 冒充"},
    {"code": "unsafe", "label": "线下安全风险"},
    {"code": "illegal", "label": "违法违规"},
    {"code": "low_quality", "label": "信息过少 / 低质"},
    {"code": "other", "label": "其他"},
]


@router.get("/moderation/reason-codes")
async def admin_moderation_reason_codes(
    request: Request,
    admin: AdminUser = Depends(require_perm("moderation:read")),
):
    _ = admin
    return ok({"items": MODERATION_REASON_CODES}, request_id=get_request_id(request))


@router.get("/sensitive-words")
async def admin_list_sensitive_words(
    request: Request,
    enabled: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("moderation:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    items, total = await TrustService(db).list_sensitive_words(
        enabled=enabled, limit=limit, offset=offset
    )
    return ok(legacy_admin_page(items, total=total, limit=limit, offset=offset), request_id=get_request_id(request))


@router.post("/sensitive-words")
async def admin_upsert_sensitive_word(
    body: SensitiveWordUpsert,
    request: Request,
    admin: AdminUser = Depends(require_perm("moderation:write")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    data = await TrustService(db).upsert_sensitive_word(
        word=body.word, category=body.category, action=body.action, enabled=body.enabled
    )
    await db.commit()
    return ok(data, request_id=get_request_id(request))
