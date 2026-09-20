"""M6 companion / buddy tables

Revision ID: 0010_companion
Revises: 0009_messaging
Create Date: 2026-09-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_companion"
down_revision: Union[str, None] = "0009_messaging"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "buddy_intents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("text", sa.String(length=280), nullable=False, server_default=""),
        sa.Column("tags", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("city", sa.String(length=64), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_buddy_intents_active", "buddy_intents", ["active"])
    op.create_index("ix_buddy_intents_city", "buddy_intents", ["city"])

    op.create_table(
        "buddy_greetings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("from_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("to_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("text", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="sent"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_buddy_greetings_from", "buddy_greetings", ["from_user_id"])
    op.create_index("ix_buddy_greetings_to", "buddy_greetings", ["to_user_id"])
    op.create_index("ix_buddy_greetings_status", "buddy_greetings", ["status"])

    op.create_table(
        "buddy_invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("from_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("to_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("activity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("activities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_buddy_invites_from", "buddy_invites", ["from_user_id"])
    op.create_index("ix_buddy_invites_to", "buddy_invites", ["to_user_id"])
    op.create_index("ix_buddy_invites_status", "buddy_invites", ["status"])

    op.create_table(
        "companion_profiles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("service_type", sa.String(length=16), nullable=False, server_default="offline"),
        sa.Column("specialty", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("intro", sa.Text(), nullable=False, server_default=""),
        sa.Column("response_time_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("order_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rating_avg", sa.Numeric(3, 2), nullable=False, server_default="0"),
        sa.Column("rating_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("city", sa.String(length=64), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reject_reason", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_companion_profiles_status", "companion_profiles", ["status"])
    op.create_index("ix_companion_profiles_service_type", "companion_profiles", ["service_type"])
    op.create_index("ix_companion_profiles_city", "companion_profiles", ["city"])

    op.create_table(
        "companion_services",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("companion_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companion_profiles.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=80), nullable=False),
        sa.Column("pricing_unit", sa.String(length=16), nullable=False, server_default="hour"),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("min_units", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_companion_services_companion_id", "companion_services", ["companion_id"])

    op.create_table(
        "companion_slots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("companion_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companion_profiles.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("hold_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_companion_slots_companion_id", "companion_slots", ["companion_id"])
    op.create_index("ix_companion_slots_status", "companion_slots", ["status"])
    op.create_index("ix_companion_slots_start_at", "companion_slots", ["start_at"])

    op.create_table(
        "companion_bookings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("companion_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companion_profiles.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("buyer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companion_services.id", ondelete="SET NULL"), nullable=True),
        sa.Column("slot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companion_slots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("units", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending_confirm"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.String(length=200), nullable=True),
        sa.Column("idempotency_key", sa.String(length=64), nullable=True),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("buyer_id", "idempotency_key", name="uq_booking_buyer_idem"),
    )
    op.create_index("ix_companion_bookings_companion_id", "companion_bookings", ["companion_id"])
    op.create_index("ix_companion_bookings_buyer_id", "companion_bookings", ["buyer_id"])
    op.create_index("ix_companion_bookings_status", "companion_bookings", ["status"])
    op.create_index("ix_companion_bookings_order_id", "companion_bookings", ["order_id"])

    op.create_table(
        "companion_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companion_bookings.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("companion_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companion_profiles.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("buyer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("content", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_companion_reviews_companion_id", "companion_reviews", ["companion_id"])

    op.create_table(
        "companion_leaderboard",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("period", sa.String(length=8), nullable=False),
        sa.Column("period_key", sa.String(length=16), nullable=False),
        sa.Column("companion_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companion_profiles.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("score", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("period", "period_key", "companion_id", name="uq_leaderboard_entry"),
    )
    op.create_index("ix_companion_leaderboard_period", "companion_leaderboard", ["period", "period_key"])


def downgrade() -> None:
    op.drop_table("companion_leaderboard")
    op.drop_table("companion_reviews")
    op.drop_table("companion_bookings")
    op.drop_table("companion_slots")
    op.drop_table("companion_services")
    op.drop_table("companion_profiles")
    op.drop_table("buddy_invites")
    op.drop_table("buddy_greetings")
    op.drop_table("buddy_intents")
