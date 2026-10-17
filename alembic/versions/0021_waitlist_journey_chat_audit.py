"""Activity waitlist + join note, activity journey progress, chat clear watermark and message audit.

Revision ID: 0021_waitlist_journey_chat_audit
Revises: 0020_clubs_guilds
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0021_waitlist_journey_chat_audit"
down_revision: Union[str, None] = "0020_clubs_guilds"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE activity_participants
            ADD COLUMN IF NOT EXISTS note VARCHAR(200),
            ADD COLUMN IF NOT EXISTS waitlisted_at TIMESTAMPTZ
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS activity_journeys (
            id UUID PRIMARY KEY,
            activity_id UUID NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            steps JSONB NOT NULL DEFAULT '{}'::jsonb,
            feedback JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_activity_journey UNIQUE (activity_id, user_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_activity_journeys_activity_id ON activity_journeys (activity_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_activity_journeys_user_id ON activity_journeys (user_id)")

    op.execute("ALTER TABLE conversation_members ADD COLUMN IF NOT EXISTS cleared_at TIMESTAMPTZ")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_message_events (
            id UUID PRIMARY KEY,
            conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            message_id VARCHAR(64) NOT NULL,
            actor_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            kind VARCHAR(16) NOT NULL,
            sent_at TIMESTAMPTZ,
            body_preview VARCHAR(240),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_chat_message_events_conversation_id ON chat_message_events (conversation_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_chat_message_events_message_id ON chat_message_events (message_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_chat_message_events_actor_id ON chat_message_events (actor_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_chat_message_events_created_at ON chat_message_events (created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chat_message_events")
    op.execute("ALTER TABLE conversation_members DROP COLUMN IF EXISTS cleared_at")
    op.execute("DROP TABLE IF EXISTS activity_journeys")
    op.execute("ALTER TABLE activity_participants DROP COLUMN IF EXISTS waitlisted_at, DROP COLUMN IF EXISTS note")
