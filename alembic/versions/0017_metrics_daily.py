"""Daily product metrics for the ops dashboard.

Revision ID: 0017_metrics_daily
Revises: 0016_analytics_events
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0017_metrics_daily"
down_revision: Union[str, None] = "0016_analytics_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE metrics_daily (
            day DATE PRIMARY KEY,
            dau INTEGER NOT NULL DEFAULT 0,
            new_users INTEGER NOT NULL DEFAULT 0,
            activities_published INTEGER NOT NULL DEFAULT 0,
            orders_paid INTEGER NOT NULL DEFAULT 0,
            gmv_cents BIGINT NOT NULL DEFAULT 0,
            funnel JSONB NOT NULL DEFAULT '{}'::jsonb,
            retention JSONB NOT NULL DEFAULT '{}'::jsonb,
            computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS metrics_daily")
