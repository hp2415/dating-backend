"""M8 ops / config ORM models."""

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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base


class TaxonomyKind(str, Enum):
    ACTIVITY_CATEGORY = "activity_category"
    INTEREST = "interest"
    CITY = "city"
    COMPANION_SPECIALTY = "companion_specialty"


class ShelfLayout(str, Enum):
    HERO = "hero"
    RAIL = "rail"
    GRID = "grid"
    LIST = "list"


class ShelfRuleType(str, Enum):
    MANUAL = "manual"
    QUERY = "query"
    ALGO = "algo"


class NotificationCategory(str, Enum):
    ACTIVITY = "activity"
    BUDDY = "buddy"
    BOOKING = "booking"
    MESSAGE = "message"
    COMMUNITY = "community"
    SYSTEM = "system"


class PushPlatform(str, Enum):
    IOS = "ios"
    ANDROID = "android"


class PushProvider(str, Enum):
    APNS = "apns"
    FCM = "fcm"
    HMS = "hms"
    MIPUSH = "mipush"
    OPPO = "oppo"
    VIVO = "vivo"


class CampaignStatus(str, Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    SENDING = "sending"
    SENT = "sent"
    CANCELLED = "cancelled"


class AnnouncementStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class FeedbackStatus(str, Enum):
    OPEN = "open"
    REPLIED = "replied"
    CLOSED = "closed"


class Taxonomy(Base):
    __tablename__ = "taxonomies"
    __table_args__ = (UniqueConstraint("kind", "code", name="uq_taxonomy_kind_code"),)

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class DiscoverShelf(Base):
    __tablename__ = "discover_shelves"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(80), nullable=False)
    subtitle: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    layout: Mapped[str] = mapped_column(
        String(16), default=ShelfLayout.RAIL.value, nullable=False
    )
    rule_type: Mapped[str] = mapped_column(
        String(16), default=ShelfRuleType.MANUAL.value, nullable=False
    )
    rule: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    city_scope: Mapped[list] = mapped_column(ARRAY(String), default=list, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DiscoverShelfItem(Base):
    __tablename__ = "discover_shelf_items"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    shelf_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("discover_shelves.id", ondelete="CASCADE"), index=True
    )
    subject_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    subject_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(
        String(24), default=NotificationCategory.SYSTEM.value, nullable=False
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    deep_link: Mapped[Optional[str]] = mapped_column(String(240), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class PushToken(Base):
    __tablename__ = "push_tokens"
    __table_args__ = (UniqueConstraint("user_id", "device_id", name="uq_push_token_user_device"),)

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_id: Mapped[str] = mapped_column(String(128), nullable=False)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str] = mapped_column(
        String(16), default=PushProvider.FCM.value, nullable=False
    )
    token: Mapped[str] = mapped_column(String(512), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PushCampaign(Base):
    __tablename__ = "push_campaigns"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    deep_link: Mapped[Optional[str]] = mapped_column(String(240), nullable=True)
    audience: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default=CampaignStatus.DRAFT.value, nullable=False, index=True
    )
    sent_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    open_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[Optional[PyUUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Announcement(Base):
    __tablename__ = "announcements"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    audience: Mapped[str] = mapped_column(String(32), default="all", nullable=False)
    publish_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default=AnnouncementStatus.DRAFT.value, nullable=False, index=True
    )
    created_by: Mapped[Optional[PyUUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Feedback(Base):
    __tablename__ = "feedbacks"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(32), default="general", nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    contact: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default=FeedbackStatus.OPEN.value, nullable=False, index=True
    )
    admin_reply: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    replied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
