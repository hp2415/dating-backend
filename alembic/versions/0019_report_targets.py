"""Reports can target posts / clubs / conversations etc., not only users.

Revision ID: 0019_report_targets
Revises: 0018_profile_extras_follows
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0019_report_targets"
down_revision: Union[str, None] = "0018_profile_extras_follows"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE reports
            ADD COLUMN IF NOT EXISTS target_kind VARCHAR(16) NOT NULL DEFAULT 'user',
            ADD COLUMN IF NOT EXISTS target_id VARCHAR(64),
            ADD COLUMN IF NOT EXISTS snapshot JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )
    op.execute("ALTER TABLE reports ALTER COLUMN target_user_id DROP NOT NULL")
    op.execute("UPDATE reports SET target_id = target_user_id::text WHERE target_id IS NULL AND target_user_id IS NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_reports_target_kind ON reports (target_kind)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_reports_target_id ON reports (target_id)")


def downgrade() -> None:
    op.execute("DELETE FROM reports WHERE target_user_id IS NULL")
    op.execute("ALTER TABLE reports ALTER COLUMN target_user_id SET NOT NULL")
    op.execute("DROP INDEX IF EXISTS ix_reports_target_id")
    op.execute("DROP INDEX IF EXISTS ix_reports_target_kind")
    op.execute("ALTER TABLE reports DROP COLUMN IF EXISTS snapshot, DROP COLUMN IF EXISTS target_id, DROP COLUMN IF EXISTS target_kind")
