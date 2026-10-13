"""Optional profile extras (height, weight, MBTI, zodiac...) and user follows.

Revision ID: 0018_profile_extras_follows
Revises: 0017_metrics_daily
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0018_profile_extras_follows"
down_revision: Union[str, None] = "0017_metrics_daily"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE user_profiles
            ADD COLUMN IF NOT EXISTS height_cm INTEGER,
            ADD COLUMN IF NOT EXISTS weight_kg INTEGER,
            ADD COLUMN IF NOT EXISTS occupation VARCHAR(16),
            ADD COLUMN IF NOT EXISTS meet_radius VARCHAR(16),
            ADD COLUMN IF NOT EXISTS mbti VARCHAR(4),
            ADD COLUMN IF NOT EXISTS zodiac VARCHAR(8)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_follows (
            id UUID PRIMARY KEY,
            follower_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            followee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_user_follows_pair UNIQUE (follower_id, followee_id),
            CONSTRAINT ck_user_follows_not_self CHECK (follower_id <> followee_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_follows_follower_id ON user_follows (follower_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_follows_followee_id ON user_follows (followee_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_follows")
    op.execute(
        """
        ALTER TABLE user_profiles
            DROP COLUMN IF EXISTS zodiac,
            DROP COLUMN IF EXISTS mbti,
            DROP COLUMN IF EXISTS meet_radius,
            DROP COLUMN IF EXISTS occupation,
            DROP COLUMN IF EXISTS weight_kg,
            DROP COLUMN IF EXISTS height_cm
        """
    )
