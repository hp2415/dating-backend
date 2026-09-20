"""Admin messaging: conversations / friends / transfers / calls (read)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AdminUser,
    CallSession,
    ChatTransfer,
    Conversation,
    ConversationMember,
    Friendship,
    FriendshipStatus,
    MessageRequest,
)
from app.modules.admin.deps import require_perm
from app.shared.deps import get_db, get_request_id
from app.shared.errors import AppError
from app.shared.pagination import legacy_admin_page
from app.shared.response import ErrorCodes, ok

router = APIRouter(prefix="/admin/v1", tags=["admin-messaging"])


@router.get("/conversations")
async def admin_list_conversations(
    request: Request,
    kind: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("chat:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    filters = []
    if kind:
        filters.append(Conversation.kind == kind)
    if q:
        filters.append(
            or_(
                Conversation.title.ilike(f"%{q}%"),
                Conversation.im_conversation_id.ilike(f"%{q}%"),
            )
        )
    count_q = select(func.count()).select_from(Conversation)
    list_q = select(Conversation).order_by(Conversation.created_at.desc())
    for f in filters:
        count_q = count_q.where(f)
        list_q = list_q.where(f)
    total = int((await db.execute(count_q)).scalar_one())
    rows = list((await db.execute(list_q.limit(limit).offset(offset))).scalars().all())
    items = []
    for c in rows:
        items.append(
            {
                "id": str(c.id),
                "kind": c.kind,
                "title": c.title,
                "im_conversation_id": c.im_conversation_id,
                "owner_id": str(c.owner_id) if c.owner_id else None,
                "related_activity_id": str(c.related_activity_id) if c.related_activity_id else None,
                "status": c.status,
                "last_message_preview": c.last_message_preview,
                "last_message_at": c.last_message_at.isoformat() if c.last_message_at else None,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "member_count": await _member_count(db, c.id),
            }
        )
    return ok(legacy_admin_page(items, total=total, limit=limit, offset=offset), request_id=get_request_id(request))


@router.get("/conversations/{conversation_id}")
async def admin_get_conversation(
    conversation_id: UUID,
    request: Request,
    admin: AdminUser = Depends(require_perm("chat:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    conv = await db.get(Conversation, conversation_id)
    if conv is None:
        raise AppError(ErrorCodes.CHAT_NOT_FOUND, "会话不存在", status_code=404)
    members = list(
        (
            await db.execute(
                select(ConversationMember)
                .where(ConversationMember.conversation_id == conversation_id)
                .order_by(ConversationMember.joined_at.asc())
            )
        ).scalars().all()
    )
    return ok(
        {
            "conversation": {
                "id": str(conv.id),
                "kind": conv.kind,
                "title": conv.title,
                "im_conversation_id": conv.im_conversation_id,
                "owner_id": str(conv.owner_id) if conv.owner_id else None,
                "related_activity_id": str(conv.related_activity_id) if conv.related_activity_id else None,
                "announcement": conv.announcement,
                "status": conv.status,
                "meta": conv.meta or {},
                "created_at": conv.created_at.isoformat() if conv.created_at else None,
            },
            "members": [
                {
                    "user_id": str(m.user_id),
                    "role": m.role,
                    "status": m.status,
                    "muted": m.muted,
                    "pinned": m.pinned,
                    "joined_at": m.joined_at.isoformat() if m.joined_at else None,
                }
                for m in members
            ],
        },
        request_id=get_request_id(request),
    )


@router.get("/friendships")
async def admin_list_friendships(
    request: Request,
    user_id: UUID | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("chat:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    filters = [Friendship.status == FriendshipStatus.ACTIVE.value]
    if user_id:
        filters.append(Friendship.user_id == user_id)
    count_q = select(func.count()).select_from(Friendship)
    list_q = select(Friendship).order_by(Friendship.created_at.desc())
    for f in filters:
        count_q = count_q.where(f)
        list_q = list_q.where(f)
    total = int((await db.execute(count_q)).scalar_one())
    rows = list((await db.execute(list_q.limit(limit).offset(offset))).scalars().all())
    items = [
        {
            "id": str(r.id),
            "user_id": str(r.user_id),
            "friend_id": str(r.friend_id),
            "remark": r.remark,
            "group_name": r.group_name,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    return ok(legacy_admin_page(items, total=total, limit=limit, offset=offset), request_id=get_request_id(request))


@router.get("/message-requests")
async def admin_list_message_requests(
    request: Request,
    status: str | None = Query(default="pending"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("chat:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    filters = []
    if status:
        filters.append(MessageRequest.status == status)
    count_q = select(func.count()).select_from(MessageRequest)
    list_q = select(MessageRequest).order_by(MessageRequest.created_at.desc())
    for f in filters:
        count_q = count_q.where(f)
        list_q = list_q.where(f)
    total = int((await db.execute(count_q)).scalar_one())
    rows = list((await db.execute(list_q.limit(limit).offset(offset))).scalars().all())
    items = [
        {
            "id": str(r.id),
            "conversation_id": str(r.conversation_id),
            "from_user_id": str(r.from_user_id),
            "to_user_id": str(r.to_user_id),
            "preview_text": r.preview_text,
            "source": r.source,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    return ok(legacy_admin_page(items, total=total, limit=limit, offset=offset), request_id=get_request_id(request))


@router.get("/transfers")
async def admin_list_transfers(
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("chat:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    filters = []
    if status:
        filters.append(ChatTransfer.status == status)
    count_q = select(func.count()).select_from(ChatTransfer)
    list_q = select(ChatTransfer).order_by(ChatTransfer.created_at.desc())
    for f in filters:
        count_q = count_q.where(f)
        list_q = list_q.where(f)
    total = int((await db.execute(count_q)).scalar_one())
    rows = list((await db.execute(list_q.limit(limit).offset(offset))).scalars().all())
    items = [
        {
            "id": str(r.id),
            "conversation_id": str(r.conversation_id) if r.conversation_id else None,
            "from_user_id": str(r.from_user_id),
            "to_user_id": str(r.to_user_id),
            "amount_cents": r.amount_cents,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]
    return ok(legacy_admin_page(items, total=total, limit=limit, offset=offset), request_id=get_request_id(request))


@router.get("/calls")
async def admin_list_calls(
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("chat:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    filters = []
    if status:
        filters.append(CallSession.status == status)
    count_q = select(func.count()).select_from(CallSession)
    list_q = select(CallSession).order_by(CallSession.created_at.desc())
    for f in filters:
        count_q = count_q.where(f)
        list_q = list_q.where(f)
    total = int((await db.execute(count_q)).scalar_one())
    rows = list((await db.execute(list_q.limit(limit).offset(offset))).scalars().all())
    items = [
        {
            "id": str(r.id),
            "conversation_id": str(r.conversation_id) if r.conversation_id else None,
            "caller_id": str(r.caller_id),
            "callee_id": str(r.callee_id),
            "kind": r.kind,
            "status": r.status,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    return ok(legacy_admin_page(items, total=total, limit=limit, offset=offset), request_id=get_request_id(request))


async def _member_count(db: AsyncSession, conversation_id: UUID) -> int:
    q = select(func.count()).select_from(ConversationMember).where(
        ConversationMember.conversation_id == conversation_id
    )
    return int((await db.execute(q)).scalar_one())
