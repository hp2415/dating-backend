"""B-class client APIs: settings, activity details/fee/favorite/search, community bookmark

Revision ID: 0014_b_class_apis
Revises: 0013_media_local_sms
Create Date: 2026-09-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_b_class_apis"
down_revision: Union[str, None] = "0013_media_local_sms"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "activities",
        sa.Column("fee_type", sa.String(length=16), nullable=False, server_default="free"),
    )
    op.add_column(
        "activities",
        sa.Column("fee_cents", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("activities", sa.Column("fee_note", sa.String(length=120), nullable=True))
    op.add_column("activities", sa.Column("cancel_reason", sa.String(length=500), nullable=True))
    op.add_column("activities", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "activities",
        sa.Column("favorite_count", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "activity_details",
        sa.Column("activity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("activities.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("timeline", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("gear", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("fee_included", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("fee_excluded", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("refund_notes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("prep_notes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("registration_notes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("host_note", sa.Text(), nullable=True),
        sa.Column("gallery", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "activity_favorites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("activity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("activities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("activity_id", "user_id", name="uq_activity_favorite"),
    )
    op.create_index("ix_activity_favorites_activity_id", "activity_favorites", ["activity_id"])
    op.create_index("ix_activity_favorites_user_id", "activity_favorites", ["user_id"])

    op.create_table(
        "user_settings",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("show_distance", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("show_online", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("allow_invite", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notify_activity", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notify_buddy", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notify_message", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notify_community", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("youth_mode", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("guidelines_ack_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("legal_consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.add_column(
        "community_posts",
        sa.Column("bookmark_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "community_posts",
        sa.Column("repost_count", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "community_bookmarks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("post_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("community_posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("collection_name", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("post_id", "user_id", name="uq_community_bookmark"),
    )
    op.create_index("ix_community_bookmarks_post_id", "community_bookmarks", ["post_id"])
    op.create_index("ix_community_bookmarks_user_id", "community_bookmarks", ["user_id"])

    op.create_table(
        "community_reposts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("post_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("community_posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quote_text", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("post_id", "user_id", name="uq_community_repost"),
    )
    op.create_index("ix_community_reposts_post_id", "community_reposts", ["post_id"])
    op.create_index("ix_community_reposts_user_id", "community_reposts", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_community_reposts_user_id", table_name="community_reposts")
    op.drop_index("ix_community_reposts_post_id", table_name="community_reposts")
    op.drop_table("community_reposts")
    op.drop_index("ix_community_bookmarks_user_id", table_name="community_bookmarks")
    op.drop_index("ix_community_bookmarks_post_id", table_name="community_bookmarks")
    op.drop_table("community_bookmarks")
    op.drop_column("community_posts", "repost_count")
    op.drop_column("community_posts", "bookmark_count")
    op.drop_table("user_settings")
    op.drop_index("ix_activity_favorites_user_id", table_name="activity_favorites")
    op.drop_index("ix_activity_favorites_activity_id", table_name="activity_favorites")
    op.drop_table("activity_favorites")
    op.drop_table("activity_details")
    op.drop_column("activities", "favorite_count")
    op.drop_column("activities", "cancelled_at")
    op.drop_column("activities", "cancel_reason")
    op.drop_column("activities", "fee_note")
    op.drop_column("activities", "fee_cents")
    op.drop_column("activities", "fee_type")
