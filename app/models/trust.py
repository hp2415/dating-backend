"""M7 trust / governance ORM models."""

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
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base


class TrustDomain(str, Enum):
    ACCOUNT = "account"
    ACTIVITY = "activity"
    BUDDY = "buddy"
    BOOKING = "booking"
    SOCIAL = "social"
    COMMUNITY = "community"
    ORG = "org"
    WALLET = "wallet"
    MODERATION = "moderation"


class TrustLevel(str, Enum):
    GUEST = "guest"
    NEWCOMER = "newcomer"
    TRUSTED = "trusted"
    RELIABLE_HOST = "reliable_host"
    RESTRICTED = "restricted"


class TrustBadgeKind(str, Enum):
    PHOTO_VERIFIED = "photo_verified"
    PHONE_VERIFIED = "phone_verified"
    IDENTITY_VERIFIED = "identity_verified"
    ACTIVE_MEMBER = "active_member"
    RELIABLE_HOST = "reliable_host"
    TRUSTED_NEIGHBOR = "trusted_neighbor"


class VerificationKind(str, Enum):
    PHOTO = "photo"
    REALNAME = "realname"


class VerificationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class SafetyCheckinResult(str, Enum):
    OK = "ok"
    ISSUE = "issue"


class SanctionKind(str, Enum):
    WARN = "warn"
    MUTE = "mute"
    LIMIT_PUBLISH = "limit_publish"
    LIMIT_TRADE = "limit_trade"
    BAN = "ban"


class ModerationMachineLabel(str, Enum):
    PASS = "pass"
    REVIEW = "review"
    REJECT = "reject"


class ModerationTaskStatus(str, Enum):
    PENDING = "pending"
    AUTO_PASSED = "auto_passed"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    REJECTED = "rejected"


class SensitiveWordAction(str, Enum):
    WARN = "warn"
    BLOCK = "block"
    REVIEW = "review"


class TrustEvent(Base):
    __tablename__ = "trust_events"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    actor_user_id: Mapped[Optional[PyUUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    subject_user_id: Mapped[Optional[PyUUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    domain: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(48), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"), nullable=False)
    note: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="server", nullable=False)
    dedup_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, unique=True)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class TrustScore(Base):
    __tablename__ = "trust_scores"

    user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("50"), nullable=False)
    level: Mapped[str] = mapped_column(
        String(24), default=TrustLevel.NEWCOMER.value, nullable=False
    )
    identity: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("50"), nullable=False)
    reliability: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("50"), nullable=False)
    communication: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("50"), nullable=False)
    safety: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("50"), nullable=False)
    facts: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    sample_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confidence_low: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class TrustBadge(Base):
    __tablename__ = "trust_badges"
    __table_args__ = (UniqueConstraint("user_id", "kind", name="uq_trust_badge_user_kind"),)

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="system", nullable=False)


class Verification(Base):
    __tablename__ = "verifications"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(16), default=VerificationStatus.PENDING.value, nullable=False, index=True
    )
    similarity: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3), nullable=True)
    quality_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3), nullable=True)
    evidence_media_id: Mapped[Optional[PyUUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_by: Mapped[Optional[PyUUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reject_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SafetyCheckin(Base):
    __tablename__ = "safety_checkins"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    subject_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    note: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Sanction(Base):
    __tablename__ = "sanctions"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    scope: Mapped[str] = mapped_column(String(64), default="global", nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    admin_id: Mapped[Optional[PyUUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ModerationTask(Base):
    __tablename__ = "moderation_tasks"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    target_kind: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    target_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    machine_result: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    machine_label: Mapped[str] = mapped_column(
        String(16), default=ModerationMachineLabel.REVIEW.value, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), default=ModerationTaskStatus.PENDING.value, nullable=False, index=True
    )
    assignee_admin_id: Mapped[Optional[PyUUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_by: Mapped[Optional[PyUUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reason_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    admin_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class SensitiveWord(Base):
    __tablename__ = "sensitive_words"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    word: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(32), default="general", nullable=False)
    action: Mapped[str] = mapped_column(
        String(16), default=SensitiveWordAction.REVIEW.value, nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
