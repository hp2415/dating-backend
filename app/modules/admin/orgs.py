"""Admin: clubs, guilds, chat message events."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminUser, ChatMessageEvent
from app.modules.admin.audit import write_audit
from app.modules.admin.deps import require_perm
from app.modules.clubs.service import ClubService, GuildService
from app.shared.deps import get_db, get_request_id
from app.shared.pagination import legacy_admin_page
from app.shared.response import ok

router = APIRouter(prefix="/admin/v1", tags=["admin-orgs"])


class ClubAction(BaseModel):
    action: str = Field(pattern="^(hide|unhide|dissolve)$")
    admin_note: str | None = Field(default=None, max_length=500)


class GuildUpsert(BaseModel):
    name: str | None = Field(default=None, max_length=40)
    specialty: str | None = Field(default=None, max_length=80)
    city: str | None = Field(default=None, max_length=48)
    summary: str | None = Field(default=None, max_length=500)
    tags: list[str] | None = None
    system_image: str | None = Field(default=None, max_length=40)
    price_from_cents: int | None = Field(default=None, ge=0)
    owner_user_id: UUID | None = None
    status: str | None = Field(default=None, pattern="^(active|hidden)$")


class GuildAssign(BaseModel):
    companion_user_id: UUID
    assign: bool = True


@router.get("/clubs")
async def admin_list_clubs(
    request: Request,
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    topic: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("club:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    items, total = await ClubService(db).admin_list(q=q, status=status, topic=topic, limit=limit, offset=offset)
    return ok(legacy_admin_page(items, total=total, limit=limit, offset=offset), request_id=get_request_id(request))


@router.post("/clubs/{club_id}/action")
async def admin_club_action(
    club_id: UUID,
    body: ClubAction,
    request: Request,
    admin: AdminUser = Depends(require_perm("club:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await ClubService(db).admin_set_status(club_id, action=body.action, note=body.admin_note)
    write_audit(db, admin, action=f"club_{body.action}", target_type="club", target_id=str(club_id),
                detail={"admin_note": body.admin_note})
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.get("/guilds")
async def admin_list_guilds(
    request: Request,
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("club:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    items, total = await GuildService(db).admin_list(q=q, status=status, limit=limit, offset=offset)
    return ok(legacy_admin_page(items, total=total, limit=limit, offset=offset), request_id=get_request_id(request))


@router.post("/guilds")
async def admin_create_guild(
    body: GuildUpsert,
    request: Request,
    admin: AdminUser = Depends(require_perm("club:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await GuildService(db).admin_upsert(None, body.model_dump(exclude_unset=True))
    write_audit(db, admin, action="guild_create", target_type="guild", target_id=data["id"], detail={"name": data["name"]})
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.put("/guilds/{guild_id}")
async def admin_update_guild(
    guild_id: UUID,
    body: GuildUpsert,
    request: Request,
    admin: AdminUser = Depends(require_perm("club:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await GuildService(db).admin_upsert(guild_id, body.model_dump(exclude_unset=True))
    write_audit(db, admin, action="guild_update", target_type="guild", target_id=str(guild_id),
                detail=body.model_dump(exclude_unset=True, mode="json"))
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/guilds/{guild_id}/companions")
async def admin_guild_assign(
    guild_id: UUID,
    body: GuildAssign,
    request: Request,
    admin: AdminUser = Depends(require_perm("club:write")),
    db: AsyncSession = Depends(get_db),
):
    data = await GuildService(db).admin_assign_companion(guild_id, body.companion_user_id, assign=body.assign)
    write_audit(db, admin, action="guild_assign_companion", target_type="guild", target_id=str(guild_id),
                detail={"companion_user_id": str(body.companion_user_id), "assign": body.assign})
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.get("/chat/message-events")
async def admin_message_events(
    request: Request,
    conversation_id: UUID | None = Query(default=None),
    kind: str | None = Query(default=None, pattern="^(recall|edit)$"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("chat:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    filters = []
    if conversation_id:
        filters.append(ChatMessageEvent.conversation_id == conversation_id)
    if kind:
        filters.append(ChatMessageEvent.kind == kind)
    total = int(await db.scalar(select(func.count()).select_from(ChatMessageEvent).where(*filters)) or 0)
    rows = (
        await db.execute(
            select(ChatMessageEvent).where(*filters).order_by(ChatMessageEvent.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()
    items = [
        {
            "id": str(r.id),
            "conversation_id": str(r.conversation_id),
            "message_id": r.message_id,
            "actor_id": str(r.actor_id),
            "kind": r.kind,
            "sent_at": r.sent_at.isoformat() if r.sent_at else None,
            "body_preview": r.body_preview,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    return ok(legacy_admin_page(items, total=total, limit=limit, offset=offset), request_id=get_request_id(request))
