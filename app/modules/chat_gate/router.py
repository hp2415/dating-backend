from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Match, MatchStatus, User
from app.modules.chat_gate.provider import get_im_provider
from app.modules.safety.service import is_blocked_either
from app.shared.deps import get_current_user, get_db, get_request_id
from app.shared.errors import AppError
from app.shared.response import ErrorCodes, ok

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


class ChatTokenRequest(BaseModel):
    match_id: UUID | None = None


@router.post("/token")
async def issue_chat_token(
    body: ChatTokenRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Gate: only matched users may request IM token. Provider is noop until M3 SDK."""
    if body.match_id is not None:
        result = await db.execute(select(Match).where(Match.id == body.match_id))
        match = result.scalar_one_or_none()
        if match is None or match.status != MatchStatus.ACTIVE.value:
            raise AppError(ErrorCodes.MATCH_NOT_FOUND, "匹配不存在或已失效", status_code=404)
        if user.id not in (match.user_low, match.user_high):
            raise AppError(ErrorCodes.CHAT_FORBIDDEN, "无权进入该会话", status_code=403)
        peer_id = match.user_high if match.user_low == user.id else match.user_low
        if await is_blocked_either(db, user.id, peer_id):
            raise AppError(ErrorCodes.CHAT_FORBIDDEN, "已拉黑，无法聊天", status_code=403)
    else:
        # Without match_id, still require at least one active match to get a provider token
        result = await db.execute(
            select(Match.id).where(
                Match.status == MatchStatus.ACTIVE.value,
                or_(Match.user_low == user.id, Match.user_high == user.id),
            ).limit(1)
        )
        if result.scalar_one_or_none() is None:
            raise AppError(ErrorCodes.CHAT_FORBIDDEN, "尚未匹配，无法聊天", status_code=403)

    provider = get_im_provider()
    nickname = user.profile.display_name if user.profile else "user"
    await provider.ensure_user(user.id, nickname or "user")
    token_payload = await provider.issue_token(user.id)
    return ok(token_payload, request_id=get_request_id(request))
