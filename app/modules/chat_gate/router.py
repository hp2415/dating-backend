"""Legacy chat token gate — delegates to messaging + optional match checks."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Match, MatchStatus, User
from app.modules.messaging.service import MessagingService
from app.modules.safety.service import is_blocked_either
from app.shared.deps import get_current_user, get_db, get_request_id
from app.shared.errors import AppError
from app.shared.response import ErrorCodes, ok

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


class ChatTokenRequest(BaseModel):
    match_id: UUID | None = None
    conversation_id: UUID | None = None


async def _ensure_match_access(db: AsyncSession, user: User, match_id: UUID | None) -> None:
    """When match_id is supplied, enforce membership + block checks."""
    if match_id is None:
        return
    result = await db.execute(select(Match).where(Match.id == match_id))
    match = result.scalar_one_or_none()
    if match is None or match.status != MatchStatus.ACTIVE.value:
        raise AppError(ErrorCodes.MATCH_NOT_FOUND, "匹配不存在或已失效", status_code=404)
    if user.id not in (match.user_low, match.user_high):
        raise AppError(ErrorCodes.CHAT_FORBIDDEN, "无权进入该会话", status_code=403)
    peer_id = match.user_high if match.user_low == user.id else match.user_low
    if await is_blocked_either(db, user.id, peer_id):
        raise AppError(ErrorCodes.CHAT_FORBIDDEN, "已拉黑，无法聊天", status_code=403)


@router.post("/token")
async def issue_chat_token(
    body: ChatTokenRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_match_access(db, user, body.match_id)
    data = await MessagingService(db).issue_token(user, conversation_id=body.conversation_id)
    await db.commit()
    return ok(data, request_id=get_request_id(request))
