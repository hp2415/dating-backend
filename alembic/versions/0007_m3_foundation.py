"""activities tables

Revision ID: 0007_m3_foundation
Revises: 0006_activity
Create Date: 2026-09-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_m3_foundation"
down_revision: Union[str, None] = "0006_activity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable PostGIS when the image provides it (postgis/postgis); skip on plain postgres.
    with op.get_context().autocommit_block():
        conn = op.get_bind()
        available = conn.execute(
            sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'postgis'")
        ).scalar()
        if available:
            op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS postgis"))

    op.create_table(
        "domain_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("aggregate_kind", sa.String(length=32), nullable=False),
        sa.Column("aggregate_id", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_domain_events_name", "domain_events", ["name"])
    op.create_index("ix_domain_events_aggregate_kind", "domain_events", ["aggregate_kind"])
    op.create_index("ix_domain_events_aggregate_id", "domain_events", ["aggregate_id"])
    op.create_index("ix_domain_events_status", "domain_events", ["status"])
    op.create_index("ix_domain_events_available_at", "domain_events", ["available_at"])
    op.create_index("ix_domain_events_created_at", "domain_events", ["created_at"])
    op.create_index(
        "ix_domain_events_pending_claim",
        "domain_events",
        ["status", "available_at"],
    )

    op.create_table(
        "idempotency_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("request_hash", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("response_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("scope", "key", name="uq_idempotency_scope_key"),
    )
    op.create_index("ix_idempotency_records_scope", "idempotency_records", ["scope"])
    op.create_index("ix_idempotency_records_user_id", "idempotency_records", ["user_id"])
    op.create_index("ix_idempotency_records_expires_at", "idempotency_records", ["expires_at"])


def downgrade() -> None:
    op.drop_table("idempotency_records")
    op.drop_table("domain_events")
    # Keep postgis extension — dropping may break other DBs sharing the cluster.
