"""Clubs (兴趣俱乐部), guilds (陪玩工会), activity waitlist/journey and chat audit ORM models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID as PyUUID
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base


class ClubStatus(str, Enum):
    ACTIVE = "active"
    HIDDEN = "hidden"  # taken down by ops, owner can still see it
    DISSOLVED = "dissolved"


class ClubMemberRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class ClubMemberStatus(str, Enum):
    ACTIVE = "active"
    LEFT = "left"
    KICKED = "kicked"


class Club(Base):
    __tablename__ = "clubs"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    topic: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    city: Mapped[str] = mapped_column(String(48), nullable=False, default="", index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    system_image: Mapped[str] = mapped_column(String(40), nullable=False, default="person.3")
    creator_id: Mapped[Optional[PyUUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_official: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=ClubStatus.ACTIVE.value, index=True)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    weekly_active: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conversation_id: Mapped[Optional[PyUUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    admin_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    dissolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ClubMember(Base):
    __tablename__ = "club_members"
    __table_args__ = (UniqueConstraint("club_id", "user_id", name="uq_club_member"),)

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    club_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default=ClubMemberRole.MEMBER.value)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=ClubMemberStatus.ACTIVE.value, index=True)
    nickname: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class GuildStatus(str, Enum):
    ACTIVE = "active"
    HIDDEN = "hidden"


class Guild(Base):
    """陪玩工会：由运营入驻，不对用户开放自助创建。"""

    __tablename__ = "guilds"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    specialty: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    city: Mapped[str] = mapped_column(String(48), nullable=False, default="", index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    system_image: Mapped[str] = mapped_column(String(40), nullable=False, default="person.2")
    price_from_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    owner_user_id: Mapped[Optional[PyUUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=GuildStatus.ACTIVE.value, index=True)
    conversation_id: Mapped[Optional[PyUUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GuildFollow(Base):
    __tablename__ = "guild_follows"
    __table_args__ = (UniqueConstraint("guild_id", "user_id", name="uq_guild_follow"),)

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    guild_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("guilds.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ActivityJourney(Base):
    """活动行程：报名者在「活动行程」页的进度与反馈（跨设备同步）。"""

    __tablename__ = "activity_journeys"
    __table_args__ = (UniqueConstraint("activity_id", "user_id", name="uq_activity_journey"),)

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    activity_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activities.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # {"departed": true, "arrived": true, "checked_in_at": iso, ...}
    steps: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    feedback: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ChatMessageEvent(Base):
    """Server-side audit for edit / recall (IM keeps the body; we keep who/when for governance)."""

    __tablename__ = "chat_message_events"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # recall | edit
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    body_preview: Mapped[Optional[str]] = mapped_column(String(240), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
