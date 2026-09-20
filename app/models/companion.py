"""M6 companion / buddy ORM models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID as PyUUID
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base


class BuddyGreetingStatus(str, Enum):
    SENT = "sent"
    REPLIED = "replied"
    IGNORED = "ignored"


class BuddyInviteStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"


class CompanionServiceType(str, Enum):
    VOICE = "voice"
    SPORT = "sport"
    OFFLINE = "offline"
    PHOTO = "photo"


class CompanionProfileStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    PAUSED = "paused"
    BANNED = "banned"
    REJECTED = "rejected"


class PricingUnit(str, Enum):
    HALF_HOUR = "half_hour"
    HOUR = "hour"
    SESSION = "session"
    DAY = "day"


class SlotStatus(str, Enum):
    OPEN = "open"
    HELD = "held"
    BOOKED = "booked"
    CLOSED = "closed"


class BookingStatus(str, Enum):
    PENDING_CONFIRM = "pending_confirm"
    AWAITING_PAYMENT = "awaiting_payment"
    PAID = "paid"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class LeaderboardPeriod(str, Enum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class BuddyIntent(Base):
    __tablename__ = "buddy_intents"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    text: Mapped[str] = mapped_column(String(280), default="", nullable=False)
    tags: Mapped[list] = mapped_column(ARRAY(String), default=list, nullable=False)
    city: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BuddyGreeting(Base):
    __tablename__ = "buddy_greetings"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    from_user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    to_user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=BuddyGreetingStatus.SENT.value, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class BuddyInvite(Base):
    __tablename__ = "buddy_invites"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    from_user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    to_user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    activity_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activities.id", ondelete="CASCADE"), index=True
    )
    message: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=BuddyInviteStatus.PENDING.value, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class CompanionProfile(Base):
    __tablename__ = "companion_profiles"

    user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    service_type: Mapped[str] = mapped_column(String(16), default=CompanionServiceType.OFFLINE.value, index=True)
    specialty: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    intro: Mapped[str] = mapped_column(Text, default="", nullable=False)
    response_time_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    order_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rating_avg: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("0"), nullable=False)
    rating_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=CompanionProfileStatus.PENDING.value, nullable=False, index=True
    )
    city: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    reviewed_by: Mapped[Optional[PyUUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reject_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CompanionService(Base):
    __tablename__ = "companion_services"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    companion_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companion_profiles.user_id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(80), nullable=False)
    pricing_unit: Mapped[str] = mapped_column(String(16), default=PricingUnit.HOUR.value, nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    min_units: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CompanionSlot(Base):
    __tablename__ = "companion_slots"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    companion_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companion_profiles.user_id", ondelete="CASCADE"), index=True
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=SlotStatus.OPEN.value, nullable=False, index=True)
    hold_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CompanionBooking(Base):
    __tablename__ = "companion_bookings"
    __table_args__ = (UniqueConstraint("buyer_id", "idempotency_key", name="uq_booking_buyer_idem"),)

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    companion_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companion_profiles.user_id", ondelete="CASCADE"), index=True
    )
    buyer_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    service_id: Mapped[Optional[PyUUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companion_services.id", ondelete="SET NULL"), nullable=True
    )
    slot_id: Mapped[Optional[PyUUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companion_slots.id", ondelete="SET NULL"), nullable=True
    )
    order_id: Mapped[Optional[PyUUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    units: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), default=BookingStatus.PENDING_CONFIRM.value, nullable=False, index=True
    )
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CompanionReview(Base):
    __tablename__ = "companion_reviews"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    booking_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companion_bookings.id", ondelete="CASCADE"), unique=True
    )
    companion_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companion_profiles.user_id", ondelete="CASCADE"), index=True
    )
    buyer_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CompanionLeaderboard(Base):
    __tablename__ = "companion_leaderboard"
    __table_args__ = (UniqueConstraint("period", "period_key", "companion_id", name="uq_leaderboard_entry"),)

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    period: Mapped[str] = mapped_column(String(8), nullable=False)
    period_key: Mapped[str] = mapped_column(String(16), nullable=False)
    companion_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companion_profiles.user_id", ondelete="CASCADE")
    )
    score: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
