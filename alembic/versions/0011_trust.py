"""M7 trust / governance tables

Revision ID: 0011_trust
Revises: 0010_companion
Create Date: 2026-09-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_trust"
down_revision: Union[str, None] = "0010_companion"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trust_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("subject_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("domain", sa.String(length=24), nullable=False),
        sa.Column("name", sa.String(length=48), nullable=False),
        sa.Column("value", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("note", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="server"),
        sa.Column("dedup_key", sa.String(length=128), nullable=True, unique=True),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_trust_events_subject", "trust_events", ["subject_user_id"])
    op.create_index("ix_trust_events_domain_name", "trust_events", ["domain", "name"])
    op.create_index("ix_trust_events_created_at", "trust_events", ["created_at"])

    op.create_table(
        "trust_scores",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("score", sa.Numeric(5, 2), nullable=False, server_default="50"),
        sa.Column("level", sa.String(length=24), nullable=False, server_default="newcomer"),
        sa.Column("identity", sa.Numeric(5, 2), nullable=False, server_default="50"),
        sa.Column("reliability", sa.Numeric(5, 2), nullable=False, server_default="50"),
        sa.Column("communication", sa.Numeric(5, 2), nullable=False, server_default="50"),
        sa.Column("safety", sa.Numeric(5, 2), nullable=False, server_default="50"),
        sa.Column("facts", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence_low", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    op.create_table(
        "trust_badges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="system"),
        sa.UniqueConstraint("user_id", "kind", name="uq_trust_badge_user_kind"),
    )
    op.create_index("ix_trust_badges_user_id", "trust_badges", ["user_id"])

    op.create_table(
        "verifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("similarity", sa.Numeric(4, 3), nullable=True),
        sa.Column("quality_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("evidence_media_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reject_reason", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_verifications_user_id", "verifications", ["user_id"])
    op.create_index("ix_verifications_status", "verifications", ["status"])
    op.create_index("ix_verifications_kind", "verifications", ["kind"])

    op.create_table(
        "safety_checkins",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subject_kind", sa.String(length=24), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column("note", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_safety_checkins_user_id", "safety_checkins", ["user_id"])

    op.create_table(
        "sanctions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("scope", sa.String(length=64), nullable=False, server_default="global"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("admin_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_sanctions_user_id", "sanctions", ["user_id"])
    op.create_index("ix_sanctions_kind", "sanctions", ["kind"])

    op.create_table(
        "moderation_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("target_kind", sa.String(length=24), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("machine_result", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("machine_label", sa.String(length=16), nullable=False, server_default="review"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("assignee_admin_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason_code", sa.String(length=32), nullable=True),
        sa.Column("admin_note", sa.String(length=500), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_moderation_tasks_status", "moderation_tasks", ["status"])
    op.create_index("ix_moderation_tasks_target", "moderation_tasks", ["target_kind", "target_id"])
    op.create_index("ix_moderation_tasks_priority", "moderation_tasks", ["priority"])

    op.create_table(
        "sensitive_words",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("word", sa.String(length=64), nullable=False, unique=True),
        sa.Column("category", sa.String(length=32), nullable=False, server_default="general"),
        sa.Column("action", sa.String(length=16), nullable=False, server_default="review"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("sensitive_words")
    op.drop_table("moderation_tasks")
    op.drop_table("sanctions")
    op.drop_table("safety_checkins")
    op.drop_table("verifications")
    op.drop_table("trust_badges")
    op.drop_table("trust_scores")
    op.drop_table("trust_events")
