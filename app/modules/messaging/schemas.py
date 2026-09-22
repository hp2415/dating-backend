from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ChatTokenRequest(BaseModel):
    match_id: Optional[UUID] = None
    conversation_id: Optional[UUID] = None


class OpenDirectRequest(BaseModel):
    peer_user_id: UUID
    preview: str = Field(default="", max_length=240)


class CreateGroupRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    member_ids: list[UUID] = Field(default_factory=list)


class UpdateConversationRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=120)
    announcement: Optional[str] = None


class UpdatePrefsRequest(BaseModel):
    muted: Optional[bool] = None
    pinned: Optional[bool] = None
    alias: Optional[str] = Field(default=None, max_length=64)
    mark_read: bool = False


class AddMembersRequest(BaseModel):
    member_ids: list[UUID] = Field(min_length=1)


class FriendRequestCreate(BaseModel):
    to_user_id: Optional[UUID] = None
    to_uid: Optional[str] = None
    to_phone: Optional[str] = None
    message: str = Field(default="你好，交个朋友吧", max_length=200)
    source: str = Field(default="uid", max_length=32)


class FriendRequestRespond(BaseModel):
    action: str = Field(description="accept | decline")


class FriendUpdateRequest(BaseModel):
    remark: Optional[str] = Field(default=None, max_length=64)
    group_name: Optional[str] = Field(default=None, max_length=64)


class MessageRequestRespond(BaseModel):
    action: str = Field(description="accept | reject")


class TransferCreateRequest(BaseModel):
    conversation_id: UUID
    to_user_id: UUID
    amount_cents: int = Field(ge=1)


class CallCreateRequest(BaseModel):
    conversation_id: UUID
    callee_id: UUID
    kind: str = Field(default="voice")
