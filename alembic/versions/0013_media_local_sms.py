"""Local media storage + SMS ledger

Revision ID: 0013_media_local_sms
Revises: 0012_ops
Create Date: 2026-09-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_media_local_sms"
down_revision: Union[str, None] = "0012_ops"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "media_assets",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_media_assets_deleted_at", "media_assets", ["deleted_at"])

    op.create_table(
        "sms_send_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("phone_masked", sa.String(length=32), nullable=False),
        sa.Column("scene", sa.String(length=24), nullable=False, server_default="login"),
        sa.Column("provider", sa.String(length=24), nullable=False, server_default="log"),
        sa.Column("template_code", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="sent"),
        sa.Column("provider_msg_id", sa.String(length=128), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_sms_send_logs_phone_masked", "sms_send_logs", ["phone_masked"])
    op.create_index("ix_sms_send_logs_status", "sms_send_logs", ["status"])
    op.create_index("ix_sms_send_logs_created_at", "sms_send_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_sms_send_logs_created_at", table_name="sms_send_logs")
    op.drop_index("ix_sms_send_logs_status", table_name="sms_send_logs")
    op.drop_index("ix_sms_send_logs_phone_masked", table_name="sms_send_logs")
    op.drop_table("sms_send_logs")
    op.drop_index("ix_media_assets_deleted_at", table_name="media_assets")
    op.drop_column("media_assets", "deleted_at")
