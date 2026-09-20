"""Client messaging / social APIs."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.modules.messaging.provider import im_status
from app.modules.messaging.schemas import (
    AddMembersRequest,
    CallCreateRequest,
    CreateGroupRequest,
    FriendRequestCreate,
    FriendRequestRespond,
    FriendUpdateRequest,
    MessageRequestRespond,
    OpenDirectRequest,
    TransferCreateRequest,
    UpdateConversationRequest,
    UpdatePrefsRequest,
)
from app.modules.messaging.service import MessagingService
from app.modules.messaging.uid import ensure_public_uid
from app.shared.deps import get_current_user, get_db, get_request_id
from app.shared.errors import AppError
from app.shared.pagination import page_offset
from app.shared.response import ErrorCodes, ok

router = APIRouter(tags=["messaging"])


@router.get("/api/v1/chat/status")
async def chat_status(request: Request):
    return ok(im_status(), request_id=get_request_id(request))


@router.get("/api/v1/conversations")
async def list_conversations(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await MessagingService(db).list_conversations(user.id, limit=limit, offset=offset)
    return ok(page_offset(items, total=total, limit=limit, offset=offset), request_id=get_request_id(request))


@router.get("/api/v1/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = MessagingService(db)
    conv = await svc.get_conversation(user.id, conversation_id)
    return ok(await svc.conversation_brief(conv, viewer_id=user.id), request_id=get_request_id(request))


@router.post("/api/v1/conversations/direct")
async def open_direct(
    body: OpenDirectRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await MessagingService(db).open_direct(user, body.peer_user_id, preview=body.preview)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/api/v1/conversations/group")
async def create_group(
    body: CreateGroupRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await MessagingService(db).create_group(user, title=body.title, member_ids=body.member_ids)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.put("/api/v1/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: UUID,
    body: UpdateConversationRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await MessagingService(db).update_conversation(
        user, conversation_id, title=body.title, announcement=body.announcement
    )
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.put("/api/v1/conversations/{conversation_id}/prefs")
async def update_prefs(
    conversation_id: UUID,
    body: UpdatePrefsRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await MessagingService(db).update_prefs(
        user,
        conversation_id,
        muted=body.muted,
        pinned=body.pinned,
        alias=body.alias,
        mark_read=body.mark_read,
    )
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.get("/api/v1/conversations/{conversation_id}/members")
async def list_members(
    conversation_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await MessagingService(db).list_members(user.id, conversation_id)
    return ok({"items": items}, request_id=get_request_id(request))


@router.post("/api/v1/conversations/{conversation_id}/members")
async def add_members(
    conversation_id: UUID,
    body: AddMembersRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await MessagingService(db).add_members(user, conversation_id, body.member_ids)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.delete("/api/v1/conversations/{conversation_id}/members/me")
async def leave_conversation(
    conversation_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await MessagingService(db).leave_or_kick(user, conversation_id)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.delete("/api/v1/conversations/{conversation_id}/members/{member_user_id}")
async def remove_member(
    conversation_id: UUID,
    member_user_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await MessagingService(db).leave_or_kick(user, conversation_id, target_user_id=member_user_id)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.get("/api/v1/activities/{activity_id}/conversation")
async def activity_conversation(
    activity_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await MessagingService(db).get_activity_conversation(user.id, activity_id)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.get("/api/v1/friends")
async def list_friends(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await MessagingService(db).list_friends(user.id)
    await db.commit()
    return ok({"items": items}, request_id=get_request_id(request))


@router.put("/api/v1/friends/{friend_id}")
async def update_friend(
    friend_id: UUID,
    body: FriendUpdateRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await MessagingService(db).update_friend(
        user.id, friend_id, remark=body.remark, group_name=body.group_name
    )
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.delete("/api/v1/friends/{friend_id}")
async def delete_friend(
    friend_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await MessagingService(db).delete_friend(user.id, friend_id)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/api/v1/friend-requests")
async def create_friend_request(
    body: FriendRequestCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await MessagingService(db).send_friend_request(
        user,
        to_user_id=body.to_user_id,
        to_uid=body.to_uid,
        message=body.message,
        source=body.source,
    )
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.get("/api/v1/friend-requests")
async def list_friend_requests(
    request: Request,
    direction: str = Query(default="incoming", description="incoming|sent"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await MessagingService(db).list_friend_requests(user.id, direction=direction)
    return ok({"items": items}, request_id=get_request_id(request))


@router.post("/api/v1/friend-requests/{request_id}/respond")
async def respond_friend_request(
    request_id: UUID,
    body: FriendRequestRespond,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.action not in ("accept", "decline"):
        raise AppError(ErrorCodes.FRIEND_INVALID, "action 须为 accept|decline")
    data = await MessagingService(db).respond_friend_request(user, request_id, accept=body.action == "accept")
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.get("/api/v1/message-requests")
async def list_message_requests(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await MessagingService(db).list_message_requests(user.id)
    return ok({"items": items}, request_id=get_request_id(request))


@router.post("/api/v1/message-requests/{request_id}/respond")
async def respond_message_request(
    request_id: UUID,
    body: MessageRequestRespond,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.action not in ("accept", "reject"):
        raise AppError(ErrorCodes.CHAT_INVALID, "action 须为 accept|reject")
    data = await MessagingService(db).respond_message_request(user, request_id, accept=body.action == "accept")
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/api/v1/transfers")
async def create_transfer(
    body: TransferCreateRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await MessagingService(db).create_transfer(
        user,
        conversation_id=body.conversation_id,
        to_user_id=body.to_user_id,
        amount_cents=body.amount_cents,
    )
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/api/v1/transfers/{transfer_id}/accept")
async def accept_transfer(
    transfer_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await MessagingService(db).accept_transfer(user, transfer_id)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/api/v1/transfers/{transfer_id}/cancel")
async def cancel_transfer(
    transfer_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await MessagingService(db).cancel_transfer(user, transfer_id)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/api/v1/calls")
async def start_call(
    body: CallCreateRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await MessagingService(db).start_call(
        user, conversation_id=body.conversation_id, callee_id=body.callee_id, kind=body.kind
    )
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/api/v1/calls/{call_id}/answer")
async def answer_call(
    call_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await MessagingService(db).answer_call(user, call_id)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/api/v1/calls/{call_id}/reject")
async def reject_call(
    call_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await MessagingService(db).reject_or_end_call(user, call_id, action="reject")
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/api/v1/calls/{call_id}/end")
async def end_call(
    call_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await MessagingService(db).reject_or_end_call(user, call_id, action="end")
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.get("/api/v1/calls")
async def list_calls(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await MessagingService(db).list_calls(user.id, limit=limit)
    return ok({"items": items}, request_id=get_request_id(request))


@router.get("/api/v1/users/by-uid/{uid}")
async def lookup_user_by_uid(
    uid: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _ = user
    data = await MessagingService(db).lookup_by_uid(uid)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.get("/api/v1/me/public-uid")
async def my_public_uid(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    uid = await ensure_public_uid(db, user)
    await db.commit()
    return ok({"public_uid": uid, "user_id": str(user.id)}, request_id=get_request_id(request))
