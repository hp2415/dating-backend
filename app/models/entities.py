from datetime import date, datetime
from enum import Enum
from typing import Optional
from uuid import UUID as PyUUID
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    BigInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.db import Base


class UserStatus(str, Enum):
    ACTIVE = "active"
    LIMITED = "limited"
    BANNED = "banned"
    DELETED = "deleted"


class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    UNKNOWN = "unknown"


class AuditStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class MediaType(str, Enum):
    AVATAR = "avatar"
    ALBUM = "album"
    CHAT = "chat"
    POST_IMAGE = "post_image"
    POST_VIDEO = "post_video"
    ACTIVITY_IMAGE = "activity_image"
    ACTIVITY_VIDEO = "activity_video"


class User(Base):
    __tablename__ = "users"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    phone: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    public_uid: Mapped[Optional[str]] = mapped_column(String(9), unique=True, index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=UserStatus.ACTIVE.value, nullable=False)
    discoverable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    profile_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    profile: Mapped[Optional["UserProfile"]] = relationship(back_populates="user", uselist=False)
    preference: Mapped[Optional["UserPreference"]] = relationship(back_populates="user", uselist=False)


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    birthday: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    gender: Mapped[str] = mapped_column(String(16), default=Gender.UNKNOWN.value, nullable=False)
    city: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[list] = mapped_column(ARRAY(String), default=list, nullable=False)
    avatar_media_id: Mapped[Optional[PyUUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    completion_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="profile")


class UserPreference(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    want_genders: Mapped[list] = mapped_column(ARRAY(String), default=list, nullable=False)
    age_min: Mapped[int] = mapped_column(Integer, default=18, nullable=False)
    age_max: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    max_distance_km: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="preference")


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("user_id", "device_id", name="uq_user_device"),)

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), default="android", nullable=False)
    push_token: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MediaAsset(Base):
    __tablename__ = "media_assets"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    media_type: Mapped[str] = mapped_column(String(16), default=MediaType.AVATAR.value, nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    audit_status: Mapped[str] = mapped_column(String(16), default=AuditStatus.PENDING.value, nullable=False)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class SmsSendLog(Base):
    """SMS send ledger — required before wiring a real provider."""

    __tablename__ = "sms_send_logs"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    phone_masked: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    scene: Mapped[str] = mapped_column(String(24), default="login", nullable=False)
    provider: Mapped[str] = mapped_column(String(24), default="log", nullable=False)
    template_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="sent", nullable=False, index=True)
    provider_msg_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdminRole(str, Enum):
    SUPERADMIN = "superadmin"
    AUDITOR = "auditor"
    OPERATOR = "operator"
    SUPPORT = "support"
    READONLY = "readonly"
    FINANCE = "finance"


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    role: Mapped[str] = mapped_column(String(32), default=AdminRole.READONLY.value, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    admin_id: Mapped[Optional[PyUUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    target_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    detail: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SwipeAction(str, Enum):
    LIKE = "like"
    PASS = "pass"


class MatchStatus(str, Enum):
    ACTIVE = "active"
    UNMATCHED = "unmatched"
    BLOCKED = "blocked"


class Swipe(Base):
    __tablename__ = "swipes"
    __table_args__ = (UniqueConstraint("actor_id", "target_id", name="uq_swipe_pair"),)

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    actor_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    target_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (UniqueConstraint("user_low", "user_high", name="uq_match_pair"),)

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_low: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    user_high: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), default=MatchStatus.ACTIVE.value, nullable=False)
    # Reserved for third-party IM conversation id (M3+)
    im_conversation_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    matched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    unmatched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Block(Base):
    __tablename__ = "blocks"
    __table_args__ = (UniqueConstraint("blocker_id", "blocked_id", name="uq_block_pair"),)

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    blocker_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    blocked_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReportReason(str, Enum):
    SPAM = "spam"
    HARASSMENT = "harassment"
    INAPPROPRIATE = "inappropriate"
    FAKE = "fake"
    OTHER = "other"


class ReportStatus(str, Enum):
    PENDING = "pending"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ReportResolution(str, Enum):
    DISMISS = "dismiss"
    WARN = "warn"
    LIMIT = "limit"
    BAN = "ban"


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    reporter_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    target_user_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=ReportStatus.PENDING.value, nullable=False, index=True)
    resolution: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    resolved_by: Mapped[Optional[PyUUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    admin_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class PostStatus(str, Enum):
    PENDING = "pending"
    PUBLISHED = "published"
    REJECTED = "rejected"
    DELETED = "deleted"


class CommunityPost(Base):
    __tablename__ = "community_posts"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    author_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # [{type: image|video, url, media_id?}] â OSS upload reserved via media_id / STS post_* types
    media: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=PostStatus.PENDING.value, nullable=False, index=True)
    like_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    comment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reviewed_by: Mapped[Optional[PyUUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    admin_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CommunityComment(Base):
    __tablename__ = "community_comments"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    post_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("community_posts.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="visible", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class CommunityLike(Base):
    __tablename__ = "community_likes"
    __table_args__ = (UniqueConstraint("post_id", "user_id", name="uq_community_like"),)

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    post_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("community_posts.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ActivityStatus(str, Enum):
    PENDING = "pending"
    PUBLISHED = "published"
    REJECTED = "rejected"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class ParticipantRole(str, Enum):
    HOST = "host"
    MEMBER = "member"


class ParticipantStatus(str, Enum):
    JOINED = "joined"
    QUIT = "quit"
    KICKED = "kicked"


class Activity(Base):
    """æ¾æ­å­æ´»å¨ï¼è¯¦æé¡µèåæ é¢/å¾ç/å°å/æ¶é´/æ¥åã"""

    __tablename__ = "activities"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    host_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(32), default="other", nullable=False, index=True)
    city: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    address: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    # Map SDK reserved: store coords now, render later via LocationProvider
    lat: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    lng: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    start_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    end_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    capacity: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    join_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # [{type: image|video, url, media_id?}]
    media: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=ActivityStatus.PENDING.value, nullable=False, index=True)
    like_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    comment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reviewed_by: Mapped[Optional[PyUUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    admin_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ActivityParticipant(Base):
    __tablename__ = "activity_participants"
    __table_args__ = (UniqueConstraint("activity_id", "user_id", name="uq_activity_participant"),)

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    activity_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activities.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16), default=ParticipantRole.MEMBER.value, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=ParticipantStatus.JOINED.value, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ActivityComment(Base):
    """æ´»å¨å¨æè¯è®ºï¼åç¤¾åºå¸å­äºå¨å¹¶å¥æ´»å¨ï¼ã"""

    __tablename__ = "activity_comments"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    activity_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activities.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="visible", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class ActivityLike(Base):
    __tablename__ = "activity_likes"
    __table_args__ = (UniqueConstraint("activity_id", "user_id", name="uq_activity_like"),)

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    activity_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activities.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DomainEventStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class DomainEvent(Base):
    """Transactional outbox â API writes here; ARQ worker drains."""

    __tablename__ = "domain_events"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    aggregate_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=DomainEventStatus.PENDING.value, nullable=False, index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class IdempotencyRecord(Base):
    """Generic Idempotency-Key store for write endpoints.

    Uniqueness is ``(scope, key)``. Include user id in ``key`` when scoping per user
    (e.g. ``f"{user_id}:{client_key}"``).
    """

    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("scope", "key", name="uq_idempotency_scope_key"),)

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    scope: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[Optional[PyUUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    request_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    response_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ââ M4 commerce ââââââââââââââââââââââââââââââââââââââââââââââ


class OrderKind(str, Enum):
    ACTIVITY = "activity"
    COMPANION_BOOKING = "companion_booking"
    MEMBERSHIP = "membership"
    WALLET_TOPUP = "wallet_topup"


class OrderStatus(str, Enum):
    CREATED = "created"
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    CLOSED = "closed"
    REFUNDING = "refunding"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class PayMethod(str, Enum):
    WALLET = "wallet"
    WECHAT = "wechat"
    ALIPAY = "alipay"
    APPLE_PAY = "apple_pay"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CLOSED = "closed"


class RefundStatus(str, Enum):
    SUBMITTED = "submitted"
    PROCESSING = "processing"
    COMPLETED = "completed"
    REJECTED = "rejected"


class RefundInitiator(str, Enum):
    USER = "user"
    SYSTEM = "system"
    ADMIN = "admin"


class WalletLedgerKind(str, Enum):
    TOP_UP = "top_up"
    WELCOME = "welcome"
    ACTIVITY_PAYMENT = "activity_payment"
    ACTIVITY_REFUND = "activity_refund"
    BOOKING_PAYMENT = "booking_payment"
    BOOKING_REFUND = "booking_refund"
    TRANSFER_OUT = "transfer_out"
    TRANSFER_IN = "transfer_in"
    TRANSFER_REFUND = "transfer_refund"
    MEMBERSHIP = "membership"


class MembershipStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class CredentialStyle(str, Enum):
    EVENT_TICKET = "event_ticket"
    STORE_CARD = "store_card"
    COUPON = "coupon"


class CredentialStatus(str, Enum):
    VALID = "valid"
    USED = "used"
    VOIDED = "voided"
    EXPIRED = "expired"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    order_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    user_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    subject_id: Mapped[Optional[PyUUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    subject_title: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    discount_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    payable_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=OrderStatus.CREATED.value, nullable=False, index=True)
    pay_method: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    order_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_txn_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=PaymentStatus.PENDING.value, nullable=False, index=True)
    raw_notify: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    client_params: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Refund(Base):
    __tablename__ = "refunds"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    order_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    detail: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    initiator: Mapped[str] = mapped_column(String(16), default=RefundInitiator.USER.value, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=RefundStatus.SUBMITTED.value, nullable=False, index=True)
    provider_refund_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    admin_id: Mapped[Optional[PyUUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )
    admin_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    processing_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WalletAccount(Base):
    __tablename__ = "wallet_accounts"

    user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    balance_cents: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    frozen_cents: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WalletLedger(Base):
    __tablename__ = "wallet_ledger"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    subtitle: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    balance_delta_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_after_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    related_order_id: Mapped[Optional[PyUUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    method: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class MembershipPlan(Base):
    __tablename__ = "membership_plans"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(64), nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    benefits: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Membership(Base):
    __tablename__ = "memberships"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan_code: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=MembershipStatus.ACTIVE.value, nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_order_id: Mapped[Optional[PyUUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Credential(Base):
    __tablename__ = "credentials"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    style: Mapped[str] = mapped_column(String(32), nullable=False)
    serial_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    related_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    related_id: Mapped[Optional[PyUUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    fields: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    barcode_message: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    relevant_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=CredentialStatus.VALID.value, nullable=False, index=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CredentialRegistration(Base):
    __tablename__ = "credential_registrations"
    __table_args__ = (UniqueConstraint("credential_id", "device_library_id", name="uq_credential_device"),)

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    credential_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("credentials.id", ondelete="CASCADE"), index=True
    )
    device_library_id: Mapped[str] = mapped_column(String(128), nullable=False)
    push_token: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    pass_type_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

# ©¤©¤ M5 messaging / social ©¤©¤©¤©¤©¤©¤©¤©¤©¤©¤©¤©¤©¤©¤©¤©¤©¤©¤©¤©¤©¤©¤©¤©¤©¤©¤©¤©¤©¤©¤©¤©¤©¤©¤©¤©¤


class ConversationKind(str, Enum):
    DIRECT = 'direct'
    GROUP = 'group'
    ACTIVITY = 'activity'
    CIRCLE = 'circle'
    NOTICE = 'notice'


class ConversationStatus(str, Enum):
    ACTIVE = 'active'
    ARCHIVED = 'archived'
    DISSOLVED = 'dissolved'


class MemberRole(str, Enum):
    OWNER = 'owner'
    ADMIN = 'admin'
    MEMBER = 'member'


class MemberStatus(str, Enum):
    ACTIVE = 'active'
    LEFT = 'left'
    KICKED = 'kicked'


class FriendshipStatus(str, Enum):
    ACTIVE = 'active'
    DELETED = 'deleted'


class FriendRequestStatus(str, Enum):
    PENDING = 'pending'
    ACCEPTED = 'accepted'
    DECLINED = 'declined'
    EXPIRED = 'expired'


class MessageRequestStatus(str, Enum):
    PENDING = 'pending'
    ACCEPTED = 'accepted'
    REJECTED = 'rejected'


class ChatTransferStatus(str, Enum):
    PENDING = 'pending'
    ACCEPTED = 'accepted'
    EXPIRED = 'expired'
    CANCELLED = 'cancelled'
    REFUNDED = 'refunded'


class CallKind(str, Enum):
    VOICE = 'voice'
    VIDEO = 'video'


class CallStatus(str, Enum):
    RINGING = 'ringing'
    CONNECTING = 'connecting'
    ACTIVE = 'active'
    ENDED = 'ended'
    MISSED = 'missed'
    CANCELLED = 'cancelled'
    REJECTED = 'rejected'


class Conversation(Base):
    __tablename__ = 'conversations'

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    im_conversation_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    title: Mapped[str] = mapped_column(String(120), default='', nullable=False)
    owner_id: Mapped[Optional[PyUUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True
    )
    related_activity_id: Mapped[Optional[PyUUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey('activities.id', ondelete='SET NULL'), nullable=True, index=True
    )
    related_circle_id: Mapped[Optional[PyUUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    announcement: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_message_preview: Mapped[str] = mapped_column(String(240), default='', nullable=False)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default=ConversationStatus.ACTIVE.value, nullable=False, index=True)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ConversationMember(Base):
    __tablename__ = 'conversation_members'
    __table_args__ = (UniqueConstraint('conversation_id', 'user_id', name='uq_conversation_member'),)

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('conversations.id', ondelete='CASCADE'), index=True
    )
    user_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), index=True)
    role: Mapped[str] = mapped_column(String(16), default=MemberRole.MEMBER.value, nullable=False)
    alias: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    muted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    unread_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=MemberStatus.ACTIVE.value, nullable=False, index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Friendship(Base):
    __tablename__ = 'friendships'
    __table_args__ = (UniqueConstraint('user_id', 'friend_id', name='uq_friendship_pair'),)

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), index=True)
    friend_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), index=True)
    remark: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    group_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=FriendshipStatus.ACTIVE.value, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FriendRequest(Base):
    __tablename__ = 'friend_requests'

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    from_user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), index=True
    )
    to_user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), index=True
    )
    message: Mapped[str] = mapped_column(String(200), default='', nullable=False)
    source: Mapped[str] = mapped_column(String(32), default='uid', nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=FriendRequestStatus.PENDING.value, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class MessageRequest(Base):
    __tablename__ = 'message_requests'

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('conversations.id', ondelete='CASCADE'), index=True
    )
    from_user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), index=True
    )
    to_user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), index=True
    )
    preview_text: Mapped[str] = mapped_column(String(240), default='', nullable=False)
    source: Mapped[str] = mapped_column(String(32), default='direct_message', nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=MessageRequestStatus.PENDING.value, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ChatTransfer(Base):
    __tablename__ = 'chat_transfers'

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('conversations.id', ondelete='CASCADE'), index=True
    )
    message_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    from_user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), index=True
    )
    to_user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), index=True
    )
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=ChatTransferStatus.PENDING.value, nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CallSession(Base):
    __tablename__ = 'call_sessions'

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('conversations.id', ondelete='CASCADE'), index=True
    )
    caller_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), index=True
    )
    callee_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), index=True
    )
    kind: Mapped[str] = mapped_column(String(16), default=CallKind.VOICE.value, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), default='outgoing', nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=CallStatus.RINGING.value, nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    connected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
