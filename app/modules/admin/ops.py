"""Admin ops / config: taxonomies, shelves, announcements, feedback, campaigns."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminUser
from app.modules.admin.deps import require_perm
from app.modules.ops.schemas import (
    AnnouncementCreate,
    CampaignCreate,
    CampaignSend,
    FeedbackReply,
    ShelfItemUpsert,
    ShelfUpsert,
    TaxonomyUpsert,
)
from app.modules.ops.service import OpsService
from app.shared.deps import get_db, get_request_id
from app.shared.pagination import legacy_admin_page
from app.shared.response import ok

router = APIRouter(prefix="/admin/v1", tags=["admin-ops"])


# ── taxonomies ─────────────────────────────────────────────


@router.get("/taxonomies")
async def admin_list_taxonomies(
    request: Request,
    kind: str | None = Query(default=None),
    admin: AdminUser = Depends(require_perm("config:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    items = await OpsService(db).list_taxonomies(kind=kind, enabled_only=False)
    return ok({"items": items}, request_id=get_request_id(request))


@router.post("/taxonomies")
async def admin_create_taxonomy(
    body: TaxonomyUpsert,
    request: Request,
    admin: AdminUser = Depends(require_perm("config:write")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    data = await OpsService(db).upsert_taxonomy(body)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.put("/taxonomies/{taxonomy_id}")
async def admin_update_taxonomy(
    taxonomy_id: UUID,
    body: TaxonomyUpsert,
    request: Request,
    admin: AdminUser = Depends(require_perm("config:write")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    data = await OpsService(db).upsert_taxonomy(body, taxonomy_id=taxonomy_id)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.delete("/taxonomies/{taxonomy_id}")
async def admin_delete_taxonomy(
    taxonomy_id: UUID,
    request: Request,
    admin: AdminUser = Depends(require_perm("config:write")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    data = await OpsService(db).delete_taxonomy(taxonomy_id)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


# ── discover shelves ───────────────────────────────────────


@router.get("/discover-shelves")
async def admin_list_shelves(
    request: Request,
    enabled: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("config:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    items, total = await OpsService(db).list_shelves_admin(
        limit=limit, offset=offset, enabled=enabled
    )
    return ok(
        legacy_admin_page(items, total=total, limit=limit, offset=offset),
        request_id=get_request_id(request),
    )


@router.post("/discover-shelves")
async def admin_create_shelf(
    body: ShelfUpsert,
    request: Request,
    admin: AdminUser = Depends(require_perm("config:write")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    data = await OpsService(db).upsert_shelf(body)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.put("/discover-shelves/{shelf_id}")
async def admin_update_shelf(
    shelf_id: UUID,
    body: ShelfUpsert,
    request: Request,
    admin: AdminUser = Depends(require_perm("config:write")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    data = await OpsService(db).upsert_shelf(body, shelf_id=shelf_id)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.delete("/discover-shelves/{shelf_id}")
async def admin_delete_shelf(
    shelf_id: UUID,
    request: Request,
    admin: AdminUser = Depends(require_perm("config:write")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    data = await OpsService(db).delete_shelf(shelf_id)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.get("/discover-shelves/{shelf_id}/items")
async def admin_list_shelf_items(
    shelf_id: UUID,
    request: Request,
    admin: AdminUser = Depends(require_perm("config:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    items = await OpsService(db).list_shelf_items(shelf_id)
    return ok({"items": items}, request_id=get_request_id(request))


@router.post("/discover-shelves/{shelf_id}/items")
async def admin_create_shelf_item(
    shelf_id: UUID,
    body: ShelfItemUpsert,
    request: Request,
    admin: AdminUser = Depends(require_perm("config:write")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    data = await OpsService(db).upsert_shelf_item(shelf_id, body)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.put("/discover-shelves/{shelf_id}/items/{item_id}")
async def admin_update_shelf_item(
    shelf_id: UUID,
    item_id: UUID,
    body: ShelfItemUpsert,
    request: Request,
    admin: AdminUser = Depends(require_perm("config:write")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    data = await OpsService(db).upsert_shelf_item(shelf_id, body, item_id=item_id)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.delete("/discover-shelves/{shelf_id}/items/{item_id}")
async def admin_delete_shelf_item(
    shelf_id: UUID,
    item_id: UUID,
    request: Request,
    admin: AdminUser = Depends(require_perm("config:write")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    data = await OpsService(db).delete_shelf_item(shelf_id, item_id)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


# ── announcements ──────────────────────────────────────────


@router.get("/announcements")
async def admin_list_announcements(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("config:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    items, total = await OpsService(db).list_announcements(
        published_only=False, limit=limit, offset=offset
    )
    return ok(
        legacy_admin_page(items, total=total, limit=limit, offset=offset),
        request_id=get_request_id(request),
    )


@router.post("/announcements")
async def admin_create_announcement(
    body: AnnouncementCreate,
    request: Request,
    admin: AdminUser = Depends(require_perm("config:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await OpsService(db).create_announcement(body, admin_id=admin.id)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/announcements/{announcement_id}/publish")
async def admin_publish_announcement(
    announcement_id: UUID,
    request: Request,
    admin: AdminUser = Depends(require_perm("config:write")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    data = await OpsService(db).publish_announcement(announcement_id)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


# ── feedbacks ──────────────────────────────────────────────


@router.get("/feedbacks")
async def admin_list_feedbacks(
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("config:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    items, total = await OpsService(db).list_feedbacks(
        status=status, limit=limit, offset=offset
    )
    return ok(
        legacy_admin_page(items, total=total, limit=limit, offset=offset),
        request_id=get_request_id(request),
    )


@router.post("/feedbacks/{feedback_id}/reply")
async def admin_reply_feedback(
    feedback_id: UUID,
    body: FeedbackReply,
    request: Request,
    admin: AdminUser = Depends(require_perm("config:write")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    data = await OpsService(db).reply_feedback(feedback_id, body)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


# ── push campaigns ─────────────────────────────────────────


@router.get("/push-campaigns")
async def admin_list_campaigns(
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("config:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    items, total = await OpsService(db).list_campaigns(
        status=status, limit=limit, offset=offset
    )
    return ok(
        legacy_admin_page(items, total=total, limit=limit, offset=offset),
        request_id=get_request_id(request),
    )


@router.post("/push-campaigns")
async def admin_create_campaign(
    body: CampaignCreate,
    request: Request,
    admin: AdminUser = Depends(require_perm("push:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await OpsService(db).create_campaign(body, admin_id=admin.id)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/push-campaigns/{campaign_id}/send")
async def admin_send_campaign(
    campaign_id: UUID,
    request: Request,
    body: CampaignSend | None = None,
    admin: AdminUser = Depends(require_perm("push:write")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    payload = body or CampaignSend()
    data = await OpsService(db).send_campaign(
        campaign_id, audience_override=payload.audience
    )
    await db.commit()
    return ok(data, request_id=get_request_id(request))


# ── SMS config / logs ──────────────────────────────────────


@router.get("/config/sms")
async def admin_sms_config(
    request: Request,
    admin: AdminUser = Depends(require_perm("config:read")),
):
    _ = admin
    from app.modules.auth.sms_provider import sms_status
    from app.shared.config import settings

    status = sms_status()
    return ok(
        {
            **status,
            "dev_code_configured": bool(settings.sms_dev_code),
            "whitelist_count": len(
                [p for p in settings.sms_dev_phone_whitelist.split(",") if p.strip()]
            ),
            "access_key_set": bool(settings.sms_access_key_id),
            "note": "通道切换请改服务器 .env 后重启；密钥不回显。",
        },
        request_id=get_request_id(request),
    )


@router.post("/config/sms/test-send")
async def admin_sms_test_send(
    request: Request,
    phone: str = Query(..., min_length=11, max_length=20),
    admin: AdminUser = Depends(require_perm("config:write")),
    db: AsyncSession = Depends(get_db),
):
    """Trigger a real send_sms path (log provider writes ledger)."""
    _ = admin
    from app.modules.auth.service import AuthService

    client_ip = request.client.host if request.client else None
    data = await AuthService(db).send_sms(
        phone,
        client_ip=client_ip,
        request_id=get_request_id(request),
    )
    return ok(data, request_id=get_request_id(request))


@router.get("/sms-logs")
async def admin_sms_logs(
    request: Request,
    phone: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("config:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    from sqlalchemy import func, select

    from app.models import SmsSendLog

    filters = []
    if phone:
        filters.append(SmsSendLog.phone_masked.contains(phone.replace("*", "")))
    if status:
        filters.append(SmsSendLog.status == status)
    count_q = select(func.count()).select_from(SmsSendLog)
    list_q = select(SmsSendLog).order_by(SmsSendLog.created_at.desc())
    for f in filters:
        count_q = count_q.where(f)
        list_q = list_q.where(f)
    total = int((await db.execute(count_q)).scalar_one())
    rows = (await db.execute(list_q.limit(limit).offset(offset))).scalars().all()
    items = [
        {
            "id": r.id,
            "phone_masked": r.phone_masked,
            "scene": r.scene,
            "provider": r.provider,
            "status": r.status,
            "provider_msg_id": r.provider_msg_id,
            "error_code": r.error_code,
            "error_message": r.error_message,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    return ok(
        legacy_admin_page(items, total=total, limit=limit, offset=offset),
        request_id=get_request_id(request),
    )
