"""Admin ops endpoints for M3 foundation smoke (domain events)."""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminUser
from app.modules.admin.deps import require_perm
from app.modules.events.dispatch import handler_inventory
from app.modules.events.schemas import EnqueueEventRequest
from app.modules.events.service import DomainEventService, event_to_dict
from app.shared.deps import get_db, get_request_id
from app.shared.pagination import legacy_admin_page
from app.shared.response import ok

router = APIRouter(prefix="/admin/v1/ops", tags=["admin-ops"])


@router.get("/domain-events")
async def list_domain_events(
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("dashboard:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    items, total = await DomainEventService(db).list_recent(limit=limit, offset=offset, status=status)
    data = legacy_admin_page(
        [event_to_dict(e) for e in items],
        total=total,
        limit=limit,
        offset=offset,
    )
    return ok(data, request_id=get_request_id(request))


@router.post("/domain-events")
async def enqueue_domain_event(
    body: EnqueueEventRequest,
    request: Request,
    admin: AdminUser = Depends(require_perm("config:write")),
    db: AsyncSession = Depends(get_db),
):
    event = await DomainEventService(db).enqueue(
        name=body.name,
        aggregate_kind=body.aggregate_kind,
        aggregate_id=body.aggregate_id,
        payload={**body.payload, "enqueued_by": str(admin.id)},
    )
    await db.commit()
    return ok(event_to_dict(event), request_id=get_request_id(request))


@router.get("/event-handlers")
async def list_event_handlers(
    request: Request,
    admin: AdminUser = Depends(require_perm("dashboard:read")),
):
    _ = admin
    return ok({"items": handler_inventory()}, request_id=get_request_id(request))
