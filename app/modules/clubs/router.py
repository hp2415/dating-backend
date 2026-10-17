"""Client clubs / guilds API."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.modules.clubs.service import CLUB_TOPICS, ClubService, GuildService
from app.modules.safety.service import ReportCreate, SafetyService
from app.shared.deps import get_current_user, get_db, get_request_id
from app.shared.pagination import page_offset
from app.shared.response import ok

router = APIRouter(prefix="/api/v1", tags=["clubs"])


class ClubCreate(BaseModel):
    id: UUID | None = Field(default=None, description="客户端预生成 ID，保证离线创建重试幂等")
    name: str = Field(min_length=1, max_length=40)
    topic: str = Field(min_length=1, max_length=16)
    city: str = Field(default="", max_length=48)
    summary: str = Field(min_length=1, max_length=400)
    tags: list[str] = Field(default_factory=list, max_length=12)


class ClubReport(BaseModel):
    reason: str = Field(min_length=1, max_length=40)
    detail: str | None = Field(default=None, max_length=500)


@router.get("/clubs/topics")
async def club_topics(request: Request, user: User = Depends(get_current_user)):
    _ = user
    return ok({"items": CLUB_TOPICS}, request_id=get_request_id(request))


@router.get("/clubs")
async def list_clubs(
    request: Request,
    q: str | None = Query(default=None, max_length=40),
    topic: str | None = Query(default=None, max_length=16),
    city: str | None = Query(default=None, max_length=48),
    sort: str = Query(default="active", pattern="^(active|members|newest)$"),
    scope: str = Query(default="all", pattern="^(all|joined|created)$"),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await ClubService(db).list_clubs(
        user, q=q, topic=topic, city=city, sort=sort, scope=scope, limit=limit, offset=offset
    )
    return ok(page_offset(items, total=total, limit=limit, offset=offset), request_id=get_request_id(request))


@router.post("/clubs")
async def create_club(
    body: ClubCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await ClubService(db).create(
        user, name=body.name, topic=body.topic, city=body.city, summary=body.summary, tags=body.tags,
        club_id=body.id,
    )
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.get("/clubs/{club_id}")
async def get_club(
    club_id: UUID, request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return ok(await ClubService(db).get(user, club_id), request_id=get_request_id(request))


@router.delete("/clubs/{club_id}")
async def dissolve_club(
    club_id: UUID, request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    data = await ClubService(db).dissolve(user, club_id)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/clubs/{club_id}/join")
async def join_club(
    club_id: UUID, request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    data = await ClubService(db).join(user, club_id)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/clubs/{club_id}/leave")
async def leave_club(
    club_id: UUID, request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    data = await ClubService(db).leave(user, club_id)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.get("/clubs/{club_id}/members")
async def club_members(
    club_id: UUID,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await ClubService(db).members(user, club_id, limit=limit, offset=offset)
    return ok(page_offset(items, total=total, limit=limit, offset=offset), request_id=get_request_id(request))


@router.delete("/clubs/{club_id}/members/{member_user_id}")
async def kick_club_member(
    club_id: UUID,
    member_user_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await ClubService(db).kick(user, club_id, member_user_id)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/clubs/{club_id}/chat")
async def club_chat(
    club_id: UUID, request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    data = await ClubService(db).chat(user, club_id)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/clubs/{club_id}/report")
async def report_club(
    club_id: UUID,
    body: ClubReport,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await SafetyService(db).create_report(
        user,
        ReportCreate(target_kind="club", target_id=str(club_id), reason=body.reason, detail=body.detail),
    )
    return ok(data, request_id=get_request_id(request))


# ── guilds ─────────────────────────────────────────────────


@router.get("/guilds")
async def list_guilds(
    request: Request,
    q: str | None = Query(default=None, max_length=40),
    city: str | None = Query(default=None, max_length=48),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await GuildService(db).list_guilds(user, city=city, q=q, limit=limit, offset=offset)
    return ok(page_offset(items, total=total, limit=limit, offset=offset), request_id=get_request_id(request))


@router.get("/guilds/{guild_id}")
async def get_guild(
    guild_id: UUID, request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return ok(await GuildService(db).get(user, guild_id), request_id=get_request_id(request))


@router.post("/guilds/{guild_id}/follow")
async def follow_guild(
    guild_id: UUID, request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    data = await GuildService(db).follow(user, guild_id, follow=True)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.delete("/guilds/{guild_id}/follow")
async def unfollow_guild(
    guild_id: UUID, request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    data = await GuildService(db).follow(user, guild_id, follow=False)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/guilds/{guild_id}/chat")
async def guild_chat(
    guild_id: UUID, request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    data = await GuildService(db).chat(user, guild_id)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/guilds/{guild_id}/report")
async def report_guild(
    guild_id: UUID,
    body: ClubReport,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await SafetyService(db).create_report(
        user,
        ReportCreate(target_kind="guild", target_id=str(guild_id), reason=body.reason, detail=body.detail),
    )
    return ok(data, request_id=get_request_id(request))
