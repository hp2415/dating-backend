"""Analytics v2: richer event columns, device registry, daily aggregate tables, WAU/MAU columns.

Revision ID: 0022_analytics_v2
Revises: 0021_waitlist_journey_chat_audit
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0022_analytics_v2"
down_revision: Union[str, None] = "0021_waitlist_journey_chat_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Parent-table ALTERs cascade to every existing and future partition.
    op.execute(
        """
        ALTER TABLE analytics_events
            ADD COLUMN IF NOT EXISTS schema_version SMALLINT NOT NULL DEFAULT 1,
            ADD COLUMN IF NOT EXISTS sdk_version VARCHAR(16),
            ADD COLUMN IF NOT EXISTS channel VARCHAR(32),
            ADD COLUMN IF NOT EXISTS experiments JSONB,
            ADD COLUMN IF NOT EXISTS object_type VARCHAR(24),
            ADD COLUMN IF NOT EXISTS object_id VARCHAR(64),
            ADD COLUMN IF NOT EXISTS duration_ms INTEGER,
            ADD COLUMN IF NOT EXISTS seq INTEGER,
            ADD COLUMN IF NOT EXISTS client_ts TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS skew_ms INTEGER
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_analytics_events_object
            ON analytics_events (object_type, object_id, received_at) WHERE object_id IS NOT NULL
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_analytics_events_session ON analytics_events (session_id, received_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_analytics_events_anon ON analytics_events (anon_id, received_at)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analytics_devices (
            anon_id VARCHAR(64) PRIMARY KEY,
            first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            user_id UUID NULL,
            platform VARCHAR(16) NOT NULL DEFAULT 'android',
            first_app_version VARCHAR(32) NULL,
            app_version VARCHAR(32) NULL,
            channel VARCHAR(32) NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_analytics_devices_first_seen ON analytics_devices (first_seen_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_analytics_devices_user ON analytics_devices (user_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analytics_daily_event (
            day DATE NOT NULL,
            event_name VARCHAR(64) NOT NULL,
            screen VARCHAR(64) NOT NULL DEFAULT '',
            platform VARCHAR(16) NOT NULL DEFAULT 'android',
            events BIGINT NOT NULL DEFAULT 0,
            users INTEGER NOT NULL DEFAULT 0,
            sessions INTEGER NOT NULL DEFAULT 0,
            avg_duration_ms INTEGER NULL,
            PRIMARY KEY (day, event_name, screen, platform)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analytics_daily_object (
            day DATE NOT NULL,
            object_type VARCHAR(24) NOT NULL,
            object_id VARCHAR(64) NOT NULL,
            exposures INTEGER NOT NULL DEFAULT 0,
            exposed_users INTEGER NOT NULL DEFAULT 0,
            clicks INTEGER NOT NULL DEFAULT 0,
            details INTEGER NOT NULL DEFAULT 0,
            conversions INTEGER NOT NULL DEFAULT 0,
            paid INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (day, object_type, object_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_analytics_daily_object_obj ON analytics_daily_object (object_type, object_id)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analytics_daily_funnel (
            day DATE NOT NULL,
            funnel VARCHAR(32) NOT NULL,
            step_index SMALLINT NOT NULL,
            event_name VARCHAR(64) NOT NULL,
            users INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (day, funnel, step_index)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analytics_daily_perf (
            day DATE NOT NULL,
            metric VARCHAR(80) NOT NULL,
            app_version VARCHAR(32) NOT NULL DEFAULT '',
            n INTEGER NOT NULL DEFAULT 0,
            avg_ms INTEGER NULL,
            p50_ms INTEGER NULL,
            p90_ms INTEGER NULL,
            p99_ms INTEGER NULL,
            PRIMARY KEY (day, metric, app_version)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE metrics_daily
            ADD COLUMN IF NOT EXISTS wau INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS mau INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS sessions INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS avg_session_seconds INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS new_devices INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS device_retention JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS analytics_daily_perf")
    op.execute("DROP TABLE IF EXISTS analytics_daily_funnel")
    op.execute("DROP TABLE IF EXISTS analytics_daily_object")
    op.execute("DROP TABLE IF EXISTS analytics_daily_event")
    op.execute("DROP TABLE IF EXISTS analytics_devices")
    op.execute(
        """
        ALTER TABLE metrics_daily
            DROP COLUMN IF EXISTS wau, DROP COLUMN IF EXISTS mau, DROP COLUMN IF EXISTS sessions,
            DROP COLUMN IF EXISTS avg_session_seconds, DROP COLUMN IF EXISTS new_devices,
            DROP COLUMN IF EXISTS device_retention
        """
    )
    op.execute("DROP INDEX IF EXISTS ix_analytics_events_object")
    op.execute("DROP INDEX IF EXISTS ix_analytics_events_session")
    op.execute("DROP INDEX IF EXISTS ix_analytics_events_anon")
    op.execute(
        """
        ALTER TABLE analytics_events
            DROP COLUMN IF EXISTS schema_version, DROP COLUMN IF EXISTS sdk_version, DROP COLUMN IF EXISTS channel,
            DROP COLUMN IF EXISTS experiments, DROP COLUMN IF EXISTS object_type, DROP COLUMN IF EXISTS object_id,
            DROP COLUMN IF EXISTS duration_ms, DROP COLUMN IF EXISTS seq, DROP COLUMN IF EXISTS client_ts,
            DROP COLUMN IF EXISTS skew_ms
        """
    )
