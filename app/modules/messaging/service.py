"""Conversations, friends, transfers, calls — metadata layer; message bodies via IM."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Activity,
    CallSession,
    CallStatus,
    ChatTransfer,
    ChatTransferStatus,
    Conversation,
    ConversationKind,
    ConversationMember,
    ConversationStatus,
    FriendRequest,
    FriendRequestStatus,
    Friendship,
    FriendshipStatus,
    MemberRole,
    MemberStatus,
    MessageRequest,
    MessageRequestStatus,
    User,
    UserProfile,
    WalletLedgerKind,
)
from app.modules.commerce.wallet import WalletService
from app.modules.events.service import DomainEventName, DomainEventService
from app.modules.messaging.provider import get_im_provider, im_status
from app.modules.messaging.uid import ensure_public_uid
from app.modules.safety.service import is_blocked_either
from app.shared.errors import AppError
from app.shared.response import ErrorCodes


class MessagingService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.im = get_im_provider()
        self.events = DomainEventService(db)

    # ── conversations ──────────────────────────────────────

    async def list_conversations(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[dict], int]:
        member_ids = select(ConversationMember.conversation_id).where(
            ConversationMember.user_id == user_id,
            ConversationMember.status == MemberStatus.ACTIVE.value,
        )
        count_q = (
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.id.in_(member_ids), Conversation.status == ConversationStatus.ACTIVE.value)
        )
        total = int((await self.db.execute(count_q)).scalar_one())
        result = await self.db.execute(
            select(Conversation)
            .where(Conversation.id.in_(member_ids), Conversation.status == ConversationStatus.ACTIVE.value)
            .order_by(Conversation.last_message_at.desc().nullslast(), Conversation.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = list(result.scalars().all())
        items = []
        for c in rows:
            items.append(await self.conversation_brief(c, viewer_id=user_id))
        return items, total

    async def get_conversation(self, user_id: UUID, conversation_id: UUID) -> Conversation:
        conv = await self.db.get(Conversation, conversation_id)
        if conv is None or conv.status == ConversationStatus.DISSOLVED.value:
            raise AppError(ErrorCodes.CHAT_NOT_FOUND, "会话不存在", status_code=404)
        member = await self._active_member(conversation_id, user_id)
        if member is None:
            raise AppError(ErrorCodes.CHAT_FORBIDDEN, "无权查看该会话", status_code=403)
        return conv

    async def open_direct(self, user: User, peer_id: UUID, *, preview: str = "") -> dict:
        if peer_id == user.id:
            raise AppError(ErrorCodes.CHAT_INVALID, "不能和自己聊天")
        peer = await self.db.get(User, peer_id)
        if peer is None:
            raise AppError(ErrorCodes.USER_NOT_FOUND, "用户不存在", status_code=404)
        if await is_blocked_either(self.db, user.id, peer_id):
            raise AppError(ErrorCodes.CHAT_FORBIDDEN, "已拉黑，无法聊天", status_code=403)

        existing = await self._find_direct(user.id, peer_id)
        if existing is not None:
            return await self.conversation_brief(existing, viewer_id=user.id)

        im_id = await self.im.open_direct(user.id, peer_id)
        peer_name = await self._display_name(peer_id)
        my_name = await self._display_name(user.id)
        conv = Conversation(
            id=uuid4(),
            kind=ConversationKind.DIRECT.value,
            im_conversation_id=im_id,
            title=peer_name,
            owner_id=user.id,
            last_message_preview=preview[:240],
            last_message_at=datetime.now(timezone.utc) if preview else None,
            status=ConversationStatus.ACTIVE.value,
            meta={"peer_names": {str(user.id): my_name, str(peer_id): peer_name}},
        )
        self.db.add(conv)
        await self.db.flush()
        await self._add_member(conv.id, user.id, MemberRole.OWNER.value)
        await self._add_member(conv.id, peer_id, MemberRole.MEMBER.value)

        are_friends = await self._are_friends(user.id, peer_id)
        if not are_friends:
            self.db.add(
                MessageRequest(
                    id=uuid4(),
                    conversation_id=conv.id,
                    from_user_id=user.id,
                    to_user_id=peer_id,
                    preview_text=preview[:240] or "你好",
                    source="direct_message",
                    status=MessageRequestStatus.PENDING.value,
                )
            )
            conv.meta = {**(conv.meta or {}), "is_message_request": True}

        await self.db.flush()
        await self.events.enqueue(
            name=DomainEventName.CONVERSATION_CREATED,
            aggregate_kind="conversation",
            aggregate_id=conv.id,
            payload={"kind": conv.kind, "user_id": str(user.id), "peer_id": str(peer_id)},
        )
        return await self.conversation_brief(conv, viewer_id=user.id)

    async def create_group(
        self, user: User, *, title: str, member_ids: list[UUID]
    ) -> dict:
        ids = []
        for mid in member_ids:
            if mid != user.id and mid not in ids:
                ids.append(mid)
        if not title.strip():
            raise AppError(ErrorCodes.CHAT_INVALID, "群名称不能为空")
        im_id = await self.im.open_group(user.id, [user.id, *ids], title.strip())
        conv = Conversation(
            id=uuid4(),
            kind=ConversationKind.GROUP.value,
            im_conversation_id=im_id,
            title=title.strip()[:120],
            owner_id=user.id,
            status=ConversationStatus.ACTIVE.value,
        )
        self.db.add(conv)
        await self.db.flush()
        await self._add_member(conv.id, user.id, MemberRole.OWNER.value)
        for mid in ids:
            await self._add_member(conv.id, mid, MemberRole.MEMBER.value)
        await self.db.flush()
        return await self.conversation_brief(conv, viewer_id=user.id)

    async def update_conversation(
        self, user: User, conversation_id: UUID, *, title: str | None, announcement: str | None
    ) -> dict:
        conv = await self.get_conversation(user.id, conversation_id)
        member = await self._active_member(conversation_id, user.id)
        if member and member.role not in {MemberRole.OWNER.value, MemberRole.ADMIN.value}:
            if title is not None or announcement is not None:
                # members may only update own prefs elsewhere
                if title is not None or announcement is not None:
                    raise AppError(ErrorCodes.CHAT_FORBIDDEN, "仅群主/管理员可修改", status_code=403)
        if title is not None:
            conv.title = title.strip()[:120]
        if announcement is not None:
            conv.announcement = announcement
        await self.db.flush()
        return await self.conversation_brief(conv, viewer_id=user.id)

    async def update_prefs(
        self,
        user: User,
        conversation_id: UUID,
        *,
        muted: bool | None,
        pinned: bool | None,
        alias: str | None,
        mark_read: bool = False,
    ) -> dict:
        await self.get_conversation(user.id, conversation_id)
        member = await self._active_member(conversation_id, user.id)
        assert member is not None
        if muted is not None:
            member.muted = muted
        if pinned is not None:
            member.pinned = pinned
        if alias is not None:
            member.alias = alias[:64] or None
        if mark_read:
            member.unread_count = 0
            member.last_read_at = datetime.now(timezone.utc)
        await self.db.flush()
        conv = await self.db.get(Conversation, conversation_id)
        return await self.conversation_brief(conv, viewer_id=user.id)  # type: ignore[arg-type]

    async def list_members(self, user_id: UUID, conversation_id: UUID) -> list[dict]:
        await self.get_conversation(user_id, conversation_id)
        result = await self.db.execute(
            select(ConversationMember).where(
                ConversationMember.conversation_id == conversation_id,
                ConversationMember.status == MemberStatus.ACTIVE.value,
            )
        )
        items = []
        for m in result.scalars().all():
            items.append(
                {
                    "user_id": str(m.user_id),
                    "display_name": await self._display_name(m.user_id),
                    "role": m.role,
                    "alias": m.alias,
                    "joined_at": m.joined_at.isoformat() if m.joined_at else None,
                }
            )
        return items

    async def add_members(self, user: User, conversation_id: UUID, member_ids: list[UUID]) -> dict:
        conv = await self.get_conversation(user.id, conversation_id)
        me = await self._active_member(conversation_id, user.id)
        if me is None or me.role not in {MemberRole.OWNER.value, MemberRole.ADMIN.value}:
            raise AppError(ErrorCodes.CHAT_FORBIDDEN, "无权拉人", status_code=403)
        for mid in member_ids:
            await self._add_member(conversation_id, mid, MemberRole.MEMBER.value)
        await self.db.flush()
        return await self.conversation_brief(conv, viewer_id=user.id)

    async def leave_or_kick(
        self, user: User, conversation_id: UUID, *, target_user_id: UUID | None = None
    ) -> dict:
        conv = await self.get_conversation(user.id, conversation_id)
        target = target_user_id or user.id
        me = await self._active_member(conversation_id, user.id)
        assert me is not None
        if target != user.id:
            if me.role not in {MemberRole.OWNER.value, MemberRole.ADMIN.value}:
                raise AppError(ErrorCodes.CHAT_FORBIDDEN, "无权移除成员", status_code=403)
            status = MemberStatus.KICKED.value
        else:
            status = MemberStatus.LEFT.value
        member = await self._active_member(conversation_id, target)
        if member:
            member.status = status
        await self.db.flush()
        return await self.conversation_brief(conv, viewer_id=user.id)

    async def ensure_activity_group(self, activity: Activity, user_id: UUID) -> Conversation:
        result = await self.db.execute(
            select(Conversation).where(
                Conversation.related_activity_id == activity.id,
                Conversation.kind == ConversationKind.ACTIVITY.value,
                Conversation.status == ConversationStatus.ACTIVE.value,
            )
        )
        conv = result.scalar_one_or_none()
        if conv is None:
            im_id = await self.im.open_group(activity.host_id, [activity.host_id, user_id], activity.title)
            conv = Conversation(
                id=uuid4(),
                kind=ConversationKind.ACTIVITY.value,
                im_conversation_id=im_id,
                title=f"{activity.title} · 活动群",
                owner_id=activity.host_id,
                related_activity_id=activity.id,
                status=ConversationStatus.ACTIVE.value,
            )
            self.db.add(conv)
            await self.db.flush()
            await self._add_member(conv.id, activity.host_id, MemberRole.OWNER.value)
        await self._add_member(conv.id, user_id, MemberRole.MEMBER.value)
        await self.db.flush()
        return conv

    async def get_activity_conversation(self, user_id: UUID, activity_id: UUID) -> dict:
        from app.models import ActivityParticipant, ParticipantStatus

        activity = await self.db.get(Activity, activity_id)
        if activity is None:
            raise AppError(ErrorCodes.ACTIVITY_NOT_FOUND, "活动不存在", status_code=404)
        part = await self.db.execute(
            select(ActivityParticipant).where(
                ActivityParticipant.activity_id == activity_id,
                ActivityParticipant.user_id == user_id,
                ActivityParticipant.status == ParticipantStatus.JOINED.value,
            )
        )
        if part.scalar_one_or_none() is None:
            raise AppError(ErrorCodes.CHAT_FORBIDDEN, "仅报名成员可进活动群", status_code=403)
        conv = await self.ensure_activity_group(activity, user_id)
        return await self.conversation_brief(conv, viewer_id=user_id)

    async def issue_token(self, user: User, *, conversation_id: UUID | None = None) -> dict:
        await ensure_public_uid(self.db, user)
        nickname = user.profile.display_name if user.profile else "user"
        await self.im.ensure_user(user.id, nickname or "user")
        if conversation_id is not None:
            await self.get_conversation(user.id, conversation_id)
        return await self.im.issue_token(user.id, conversation_id=conversation_id)

    # ── friends ────────────────────────────────────────────

    async def list_friends(self, user_id: UUID) -> list[dict]:
        result = await self.db.execute(
            select(Friendship).where(
                Friendship.user_id == user_id,
                Friendship.status == FriendshipStatus.ACTIVE.value,
            )
        )
        items = []
        for f in result.scalars().all():
            items.append(
                {
                    "user_id": str(f.friend_id),
                    "display_name": await self._display_name(f.friend_id),
                    "remark": f.remark,
                    "group_name": f.group_name,
                    "public_uid": await self._public_uid(f.friend_id),
                    "created_at": f.created_at.isoformat() if f.created_at else None,
                }
            )
        return items

    async def update_friend(
        self, user_id: UUID, friend_id: UUID, *, remark: str | None, group_name: str | None
    ) -> dict:
        result = await self.db.execute(
            select(Friendship).where(
                Friendship.user_id == user_id,
                Friendship.friend_id == friend_id,
                Friendship.status == FriendshipStatus.ACTIVE.value,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise AppError(ErrorCodes.FRIEND_NOT_FOUND, "好友不存在", status_code=404)
        if remark is not None:
            row.remark = remark[:64] or None
        if group_name is not None:
            row.group_name = group_name[:64] or None
        await self.db.flush()
        return {
            "user_id": str(friend_id),
            "remark": row.remark,
            "group_name": row.group_name,
        }

    async def delete_friend(self, user_id: UUID, friend_id: UUID) -> dict:
        for a, b in ((user_id, friend_id), (friend_id, user_id)):
            result = await self.db.execute(
                select(Friendship).where(Friendship.user_id == a, Friendship.friend_id == b)
            )
            row = result.scalar_one_or_none()
            if row:
                row.status = FriendshipStatus.DELETED.value
        await self.db.flush()
        return {"deleted": True}

    async def send_friend_request(
        self, user: User, *, to_user_id: UUID | None, to_uid: str | None, to_phone: str | None, message: str, source: str
    ) -> dict:
        if to_phone:
            peer = await self._user_by_phone(to_phone)
            to_user_id = peer.id
        elif to_uid:
            peer = await self._user_by_uid(to_uid)
            to_user_id = peer.id
        if to_user_id is None:
            raise AppError(ErrorCodes.USER_NOT_FOUND, "目标用户不存在", status_code=404)
        if to_user_id == user.id:
            raise AppError(ErrorCodes.FRIEND_INVALID, "不能添加自己")
        if await self._are_friends(user.id, to_user_id):
            raise AppError(ErrorCodes.FRIEND_ALREADY, "已经是好友", status_code=409)
        if await is_blocked_either(self.db, user.id, to_user_id):
            raise AppError(ErrorCodes.CHAT_FORBIDDEN, "已拉黑", status_code=403)

        existing = await self.db.execute(
            select(FriendRequest).where(
                FriendRequest.from_user_id == user.id,
                FriendRequest.to_user_id == to_user_id,
                FriendRequest.status == FriendRequestStatus.PENDING.value,
            )
        )
        hit = existing.scalar_one_or_none()
        if hit:
            return await self.friend_request_brief(hit)

        req = FriendRequest(
            id=uuid4(),
            from_user_id=user.id,
            to_user_id=to_user_id,
            message=(message or "")[:200],
            source=source or "uid",
            status=FriendRequestStatus.PENDING.value,
        )
        self.db.add(req)
        await self.db.flush()
        await self.events.enqueue(
            name=DomainEventName.FRIEND_REQUEST_SENT,
            aggregate_kind="friend_request",
            aggregate_id=req.id,
            payload={"from": str(user.id), "to": str(to_user_id)},
        )
        return await self.friend_request_brief(req)

    async def list_friend_requests(self, user_id: UUID, *, direction: str) -> list[dict]:
        if direction == "sent":
            stmt = select(FriendRequest).where(FriendRequest.from_user_id == user_id)
        else:
            stmt = select(FriendRequest).where(FriendRequest.to_user_id == user_id)
        stmt = stmt.order_by(FriendRequest.created_at.desc())
        result = await self.db.execute(stmt)
        items = []
        for row in result.scalars().all():
            items.append(await self.friend_request_brief(row))
        return items

    async def respond_friend_request(self, user: User, request_id: UUID, *, accept: bool) -> dict:
        req = await self.db.get(FriendRequest, request_id)
        if req is None or req.to_user_id != user.id:
            raise AppError(ErrorCodes.FRIEND_NOT_FOUND, "好友申请不存在", status_code=404)
        if req.status != FriendRequestStatus.PENDING.value:
            raise AppError(ErrorCodes.FRIEND_INVALID, "申请已处理", status_code=409)
        now = datetime.now(timezone.utc)
        req.responded_at = now
        if accept:
            req.status = FriendRequestStatus.ACCEPTED.value
            await self._create_friendship(req.from_user_id, req.to_user_id)
            await self.open_direct(user, req.from_user_id, preview="我们已成为好友")
        else:
            req.status = FriendRequestStatus.DECLINED.value
        await self.db.flush()
        return await self.friend_request_brief(req)

    # ── message requests ───────────────────────────────────

    async def list_message_requests(self, user_id: UUID) -> list[dict]:
        result = await self.db.execute(
            select(MessageRequest)
            .where(
                MessageRequest.to_user_id == user_id,
                MessageRequest.status == MessageRequestStatus.PENDING.value,
            )
            .order_by(MessageRequest.created_at.desc())
        )
        return [self.message_request_brief(r) for r in result.scalars().all()]

    async def respond_message_request(self, user: User, request_id: UUID, *, accept: bool) -> dict:
        req = await self.db.get(MessageRequest, request_id)
        if req is None or req.to_user_id != user.id:
            raise AppError(ErrorCodes.CHAT_NOT_FOUND, "消息请求不存在", status_code=404)
        if req.status != MessageRequestStatus.PENDING.value:
            raise AppError(ErrorCodes.CHAT_INVALID, "请求已处理", status_code=409)
        req.responded_at = datetime.now(timezone.utc)
        req.status = MessageRequestStatus.ACCEPTED.value if accept else MessageRequestStatus.REJECTED.value
        conv = await self.db.get(Conversation, req.conversation_id)
        if conv:
            meta = dict(conv.meta or {})
            meta["is_message_request"] = not accept
            if accept:
                meta.pop("is_message_request", None)
            conv.meta = meta
        await self.db.flush()
        return self.message_request_brief(req)

    # ── transfers ──────────────────────────────────────────

    async def create_transfer(
        self, user: User, *, conversation_id: UUID, to_user_id: UUID, amount_cents: int
    ) -> dict:
        if amount_cents < 1:
            raise AppError(ErrorCodes.ORDER_INVALID, "转账金额无效")
        await self.get_conversation(user.id, conversation_id)
        if to_user_id == user.id:
            raise AppError(ErrorCodes.CHAT_INVALID, "不能转给自己")
        # Hold funds in wallet (debit immediately; credit on accept)
        await WalletService(self.db).charge(
            user.id,
            amount_cents=amount_cents,
            kind=WalletLedgerKind.TRANSFER_OUT.value,
            title="聊天转账",
            related_order_id=None,
            method="wallet",
            subtitle=f"to {to_user_id}",
        )
        transfer = ChatTransfer(
            id=uuid4(),
            conversation_id=conversation_id,
            from_user_id=user.id,
            to_user_id=to_user_id,
            amount_cents=amount_cents,
            status=ChatTransferStatus.PENDING.value,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        self.db.add(transfer)
        await self._touch_conversation(conversation_id, f"[转账] ¥{amount_cents/100:.2f}")
        await self.db.flush()
        return self.transfer_brief(transfer)

    async def accept_transfer(self, user: User, transfer_id: UUID) -> dict:
        transfer = await self.db.get(ChatTransfer, transfer_id)
        if transfer is None or transfer.to_user_id != user.id:
            raise AppError(ErrorCodes.CHAT_NOT_FOUND, "转账不存在", status_code=404)
        if transfer.status != ChatTransferStatus.PENDING.value:
            raise AppError(ErrorCodes.CHAT_INVALID, "转账状态不可用", status_code=409)
        if transfer.expires_at < datetime.now(timezone.utc):
            transfer.status = ChatTransferStatus.EXPIRED.value
            await WalletService(self.db).credit(
                transfer.from_user_id,
                amount_cents=transfer.amount_cents,
                kind=WalletLedgerKind.TRANSFER_REFUND.value,
                title="转账过期退回",
                related_order_id=None,
                method="wallet",
            )
            await self.db.flush()
            raise AppError(ErrorCodes.CHAT_INVALID, "转账已过期", status_code=409)
        transfer.status = ChatTransferStatus.ACCEPTED.value
        await WalletService(self.db).credit(
            user.id,
            amount_cents=transfer.amount_cents,
            kind=WalletLedgerKind.TRANSFER_IN.value,
            title="收到转账",
            related_order_id=None,
            method="wallet",
        )
        await self.db.flush()
        return self.transfer_brief(transfer)

    async def cancel_transfer(self, user: User, transfer_id: UUID) -> dict:
        transfer = await self.db.get(ChatTransfer, transfer_id)
        if transfer is None or transfer.from_user_id != user.id:
            raise AppError(ErrorCodes.CHAT_NOT_FOUND, "转账不存在", status_code=404)
        if transfer.status != ChatTransferStatus.PENDING.value:
            raise AppError(ErrorCodes.CHAT_INVALID, "转账状态不可用", status_code=409)
        transfer.status = ChatTransferStatus.CANCELLED.value
        await WalletService(self.db).credit(
            user.id,
            amount_cents=transfer.amount_cents,
            kind=WalletLedgerKind.TRANSFER_REFUND.value,
            title="取消转账退回",
            related_order_id=None,
            method="wallet",
        )
        await self.db.flush()
        return self.transfer_brief(transfer)

    # ── calls ──────────────────────────────────────────────

    async def start_call(
        self, user: User, *, conversation_id: UUID, callee_id: UUID, kind: str
    ) -> dict:
        await self.get_conversation(user.id, conversation_id)
        call = CallSession(
            id=uuid4(),
            conversation_id=conversation_id,
            caller_id=user.id,
            callee_id=callee_id,
            kind=kind if kind in ("voice", "video") else "voice",
            direction="outgoing",
            status=CallStatus.RINGING.value,
            meta={"stub": True, "message": "通话信令由云 IM/RTC 承载；此处仅会话记录"},
        )
        self.db.add(call)
        await self._touch_conversation(conversation_id, f"[{kind}通话]")
        await self.db.flush()
        return self.call_brief(call)

    async def answer_call(self, user: User, call_id: UUID) -> dict:
        call = await self._get_call_for(user.id, call_id)
        if call.status not in {CallStatus.RINGING.value, CallStatus.CONNECTING.value}:
            raise AppError(ErrorCodes.CHAT_INVALID, "通话状态不可接听", status_code=409)
        call.status = CallStatus.ACTIVE.value
        call.connected_at = datetime.now(timezone.utc)
        await self.db.flush()
        return self.call_brief(call)

    async def reject_or_end_call(self, user: User, call_id: UUID, *, action: str) -> dict:
        call = await self._get_call_for(user.id, call_id)
        now = datetime.now(timezone.utc)
        if action == "reject":
            call.status = CallStatus.REJECTED.value
        elif action == "cancel":
            call.status = CallStatus.CANCELLED.value
        else:
            call.status = CallStatus.ENDED.value
            if call.connected_at:
                call.duration_seconds = int((now - call.connected_at).total_seconds())
        call.ended_at = now
        await self.db.flush()
        return self.call_brief(call)

    async def list_calls(self, user_id: UUID, *, limit: int) -> list[dict]:
        result = await self.db.execute(
            select(CallSession)
            .where(or_(CallSession.caller_id == user_id, CallSession.callee_id == user_id))
            .order_by(CallSession.started_at.desc())
            .limit(limit)
        )
        return [self.call_brief(c) for c in result.scalars().all()]

    async def lookup_by_uid(self, uid: str) -> dict:
        user = await self._user_by_uid(uid)
        await ensure_public_uid(self.db, user)
        return {
            "id": str(user.id),
            "public_uid": user.public_uid,
            "display_name": await self._display_name(user.id),
        }

    # ── briefs / helpers ───────────────────────────────────

    async def conversation_brief(self, conv: Conversation, *, viewer_id: UUID) -> dict:
        member = await self._active_member(conv.id, viewer_id)
        peer = None
        if conv.kind == ConversationKind.DIRECT.value:
            peer_id = await self._direct_peer(conv.id, viewer_id)
            if peer_id:
                peer = {
                    "user_id": str(peer_id),
                    "display_name": await self._display_name(peer_id),
                    "public_uid": await self._public_uid(peer_id),
                }
        title = conv.title
        if peer and not title:
            title = peer["display_name"]
        return {
            "id": str(conv.id),
            "kind": conv.kind,
            "im_conversation_id": conv.im_conversation_id,
            "title": title,
            "owner_id": str(conv.owner_id) if conv.owner_id else None,
            "related_activity_id": str(conv.related_activity_id) if conv.related_activity_id else None,
            "announcement": conv.announcement,
            "last_message_preview": conv.last_message_preview,
            "last_message_at": conv.last_message_at.isoformat() if conv.last_message_at else None,
            "status": conv.status,
            "peer": peer,
            "is_message_request": bool((conv.meta or {}).get("is_message_request")),
            "muted": bool(member.muted) if member else False,
            "pinned": bool(member.pinned) if member else False,
            "unread_count": int(member.unread_count) if member else 0,
            "my_role": member.role if member else None,
            "im_ready": bool(im_status().get("ready")),
        }

    async def friend_request_brief(self, req: FriendRequest) -> dict:
        return {
            "id": str(req.id),
            "from_user_id": str(req.from_user_id),
            "to_user_id": str(req.to_user_id),
            "from_display_name": await self._display_name(req.from_user_id),
            "to_display_name": await self._display_name(req.to_user_id),
            "message": req.message,
            "source": req.source,
            "status": req.status,
            "created_at": req.created_at.isoformat() if req.created_at else None,
            "responded_at": req.responded_at.isoformat() if req.responded_at else None,
        }

    def message_request_brief(self, req: MessageRequest) -> dict:
        return {
            "id": str(req.id),
            "conversation_id": str(req.conversation_id),
            "from_user_id": str(req.from_user_id),
            "to_user_id": str(req.to_user_id),
            "preview_text": req.preview_text,
            "source": req.source,
            "status": req.status,
            "created_at": req.created_at.isoformat() if req.created_at else None,
        }

    def transfer_brief(self, t: ChatTransfer) -> dict:
        return {
            "id": str(t.id),
            "conversation_id": str(t.conversation_id),
            "from_user_id": str(t.from_user_id),
            "to_user_id": str(t.to_user_id),
            "amount_cents": t.amount_cents,
            "amount_display": f"¥{t.amount_cents/100:.2f}",
            "status": t.status,
            "expires_at": t.expires_at.isoformat(),
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }

    def call_brief(self, c: CallSession) -> dict:
        return {
            "id": str(c.id),
            "conversation_id": str(c.conversation_id),
            "caller_id": str(c.caller_id),
            "callee_id": str(c.callee_id),
            "kind": c.kind,
            "status": c.status,
            "started_at": c.started_at.isoformat() if c.started_at else None,
            "connected_at": c.connected_at.isoformat() if c.connected_at else None,
            "ended_at": c.ended_at.isoformat() if c.ended_at else None,
            "duration_seconds": c.duration_seconds,
            "stub": True,
        }

    async def _add_member(self, conversation_id: UUID, user_id: UUID, role: str) -> None:
        result = await self.db.execute(
            select(ConversationMember).where(
                ConversationMember.conversation_id == conversation_id,
                ConversationMember.user_id == user_id,
            )
        )
        row = result.scalar_one_or_none()
        if row:
            row.status = MemberStatus.ACTIVE.value
            if role == MemberRole.OWNER.value:
                row.role = role
            return
        self.db.add(
            ConversationMember(
                id=uuid4(),
                conversation_id=conversation_id,
                user_id=user_id,
                role=role,
                status=MemberStatus.ACTIVE.value,
            )
        )

    async def _active_member(self, conversation_id: UUID, user_id: UUID) -> ConversationMember | None:
        result = await self.db.execute(
            select(ConversationMember).where(
                ConversationMember.conversation_id == conversation_id,
                ConversationMember.user_id == user_id,
                ConversationMember.status == MemberStatus.ACTIVE.value,
            )
        )
        return result.scalar_one_or_none()

    async def _find_direct(self, a: UUID, b: UUID) -> Conversation | None:
        # Find conversation where both are active members and kind=direct
        sub_a = select(ConversationMember.conversation_id).where(
            ConversationMember.user_id == a,
            ConversationMember.status == MemberStatus.ACTIVE.value,
        )
        sub_b = select(ConversationMember.conversation_id).where(
            ConversationMember.user_id == b,
            ConversationMember.status == MemberStatus.ACTIVE.value,
        )
        result = await self.db.execute(
            select(Conversation).where(
                Conversation.kind == ConversationKind.DIRECT.value,
                Conversation.status == ConversationStatus.ACTIVE.value,
                Conversation.id.in_(sub_a),
                Conversation.id.in_(sub_b),
            ).limit(1)
        )
        return result.scalar_one_or_none()

    async def _direct_peer(self, conversation_id: UUID, viewer_id: UUID) -> UUID | None:
        result = await self.db.execute(
            select(ConversationMember.user_id).where(
                ConversationMember.conversation_id == conversation_id,
                ConversationMember.user_id != viewer_id,
                ConversationMember.status == MemberStatus.ACTIVE.value,
            ).limit(1)
        )
        return result.scalar_one_or_none()

    async def _are_friends(self, a: UUID, b: UUID) -> bool:
        result = await self.db.execute(
            select(Friendship.id).where(
                Friendship.user_id == a,
                Friendship.friend_id == b,
                Friendship.status == FriendshipStatus.ACTIVE.value,
            )
        )
        return result.scalar_one_or_none() is not None

    async def _create_friendship(self, a: UUID, b: UUID) -> None:
        for user_id, friend_id in ((a, b), (b, a)):
            result = await self.db.execute(
                select(Friendship).where(Friendship.user_id == user_id, Friendship.friend_id == friend_id)
            )
            row = result.scalar_one_or_none()
            if row:
                row.status = FriendshipStatus.ACTIVE.value
            else:
                self.db.add(
                    Friendship(
                        id=uuid4(),
                        user_id=user_id,
                        friend_id=friend_id,
                        status=FriendshipStatus.ACTIVE.value,
                    )
                )

    async def _display_name(self, user_id: UUID) -> str:
        profile = await self.db.get(UserProfile, user_id)
        if profile and profile.display_name:
            return profile.display_name
        return "用户"

    async def _public_uid(self, user_id: UUID) -> str | None:
        user = await self.db.get(User, user_id)
        if user is None:
            return None
        return await ensure_public_uid(self.db, user)

    async def _user_by_uid(self, uid: str) -> User:
        cleaned = "".join(c for c in uid if c.isdigit())
        if len(cleaned) != 9:
            raise AppError(ErrorCodes.USER_NOT_FOUND, "UID 格式错误", status_code=404)
        result = await self.db.execute(select(User).where(User.public_uid == cleaned))
        user = result.scalar_one_or_none()
        if user is None:
            raise AppError(ErrorCodes.USER_NOT_FOUND, "用户不存在", status_code=404)
        return user

    async def _user_by_phone(self, phone: str) -> User:
        from app.modules.auth.service import normalize_phone

        cleaned = normalize_phone(phone)
        if len(cleaned) != 11:
            raise AppError(ErrorCodes.USER_NOT_FOUND, "手机号格式不正确", status_code=404)
        result = await self.db.execute(select(User).where(User.phone == cleaned))
        user = result.scalar_one_or_none()
        if user is None:
            raise AppError(ErrorCodes.USER_NOT_FOUND, "用户不存在", status_code=404)
        return user

    async def _touch_conversation(self, conversation_id: UUID, preview: str) -> None:
        conv = await self.db.get(Conversation, conversation_id)
        if conv:
            conv.last_message_preview = preview[:240]
            conv.last_message_at = datetime.now(timezone.utc)

    async def _get_call_for(self, user_id: UUID, call_id: UUID) -> CallSession:
        call = await self.db.get(CallSession, call_id)
        if call is None or user_id not in (call.caller_id, call.callee_id):
            raise AppError(ErrorCodes.CHAT_NOT_FOUND, "通话不存在", status_code=404)
        return call
