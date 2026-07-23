"""activities tables

Revision ID: 0006_activity
Revises: 0005_community
Create Date: 2026-07-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_activity"
down_revision: Union[str, None] = "0005_community"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "activities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "host_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("category", sa.String(length=32), nullable=False, server_default="other"),
        sa.Column("city", sa.String(length=64), nullable=True),
        sa.Column("address", sa.String(length=256), nullable=True),
        sa.Column("lat", sa.String(length=32), nullable=True),
        sa.Column("lng", sa.String(length=32), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("join_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("media", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("like_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("comment_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "reviewed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("admin_note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_activities_host_id", "activities", ["host_id"])
    op.create_index("ix_activities_category", "activities", ["category"])
    op.create_index("ix_activities_city", "activities", ["city"])
    op.create_index("ix_activities_status", "activities", ["status"])
    op.create_index("ix_activities_start_at", "activities", ["start_at"])
    op.create_index("ix_activities_created_at", "activities", ["created_at"])

    op.create_table(
        "activity_participants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "activity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("activities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="member"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="joined"),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("activity_id", "user_id", name="uq_activity_participant"),
    )
    op.create_index("ix_activity_participants_activity_id", "activity_participants", ["activity_id"])
    op.create_index("ix_activity_participants_user_id", "activity_participants", ["user_id"])

    op.create_table(
        "activity_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "activity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("activities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", sa.String(length=1000), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="visible"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_activity_comments_activity_id", "activity_comments", ["activity_id"])
    op.create_index("ix_activity_comments_author_id", "activity_comments", ["author_id"])
    op.create_index("ix_activity_comments_created_at", "activity_comments", ["created_at"])

    op.create_table(
        "activity_likes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "activity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("activities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("activity_id", "user_id", name="uq_activity_like"),
    )
    op.create_index("ix_activity_likes_activity_id", "activity_likes", ["activity_id"])
    op.create_index("ix_activity_likes_user_id", "activity_likes", ["user_id"])


def downgrade() -> None:
    op.drop_table("activity_likes")
    op.drop_table("activity_comments")
    op.drop_table("activity_participants")
    op.drop_table("activities")
