"""Client analytics events (partitioned) plus a dedupe ledger.

PostgreSQL unique indexes on a partitioned table must include the partition
key, so event_id dedupe lives in analytics_event_dedupe.

Revision ID: 0016_analytics_events
Revises: 0015_user_password
"""

from datetime import date
from typing import Sequence, Union

from alembic import op

revision: str = "0016_analytics_events"
down_revision: Union[str, None] = "0015_user_password"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _month_start(year: int, month: int) -> date:
    return date(year, month, 1)


def _add_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE analytics_event_dedupe (
            event_id UUID PRIMARY KEY,
            received_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_analytics_event_dedupe_received ON analytics_event_dedupe (received_at)")
    op.execute(
        """
        CREATE TABLE analytics_events (
            id BIGSERIAL,
            event_id UUID NOT NULL,
            event_name VARCHAR(64) NOT NULL,
            user_id UUID NULL,
            anon_id VARCHAR(64) NOT NULL,
            session_id VARCHAR(64) NOT NULL,
            screen VARCHAR(64) NULL,
            referrer_screen VARCHAR(64) NULL,
            props JSONB NOT NULL DEFAULT '{}'::jsonb,
            platform VARCHAR(16) NOT NULL DEFAULT 'android',
            app_version VARCHAR(32) NULL,
            build_type VARCHAR(16) NULL,
            os_version VARCHAR(32) NULL,
            device_model VARCHAR(64) NULL,
            network_type VARCHAR(16) NULL,
            city VARCHAR(32) NULL,
            ip_hash VARCHAR(64) NULL,
            occurred_at TIMESTAMPTZ NOT NULL,
            received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id, received_at)
        ) PARTITION BY RANGE (received_at)
        """
    )
    op.execute(
        "CREATE INDEX ix_analytics_events_name_time ON analytics_events (event_name, received_at)"
    )
    op.execute(
        "CREATE INDEX ix_analytics_events_user_time ON analytics_events (user_id, received_at)"
    )

    today = date.today()
    for offset in range(0, 3):
        year, month = _add_month(today.year, today.month, offset)
        start = _month_start(year, month)
        next_year, next_month = _add_month(year, month, 1)
        end = _month_start(next_year, next_month)
        name = f"analytics_events_{year:04d}{month:02d}"
        op.execute(
            f"""
            CREATE TABLE {name} PARTITION OF analytics_events
            FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')
            """
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS analytics_events")
    op.execute("DROP TABLE IF EXISTS analytics_event_dedupe")
