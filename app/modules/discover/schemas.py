from datetime import date
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CardOut(BaseModel):
    id: UUID
    display_name: str
    age: Optional[int] = None
    city: Optional[str] = None
    bio: Optional[str] = None
    tags: list[str] = []
    avatar_url: Optional[str] = None
    gender: str = "unknown"
    completion_score: int = 0


class DiscoverCardsOut(BaseModel):
    items: list[CardOut]
    next_cursor: Optional[str] = None
    remaining_estimate: int = 0


class SwipeRequest(BaseModel):
    target_user_id: UUID
    action: str = Field(pattern="^(like|pass)$")
    idempotency_key: Optional[str] = Field(default=None, max_length=64)


class MatchBrief(BaseModel):
    id: UUID
    peer: CardOut
    matched_at: str
    status: str
    im_conversation_id: Optional[str] = None


class SwipeResult(BaseModel):
    recorded: bool
    matched: bool
    match: Optional[MatchBrief] = None
