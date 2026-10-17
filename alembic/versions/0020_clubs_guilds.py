"""Clubs (user-created interest clubs) and guilds (ops-managed companion guilds).

Revision ID: 0020_clubs_guilds
Revises: 0019_report_targets
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0020_clubs_guilds"
down_revision: Union[str, None] = "0019_report_targets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clubs (
            id UUID PRIMARY KEY,
            name VARCHAR(40) NOT NULL,
            topic VARCHAR(16) NOT NULL,
            city VARCHAR(48) NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            tags JSONB NOT NULL DEFAULT '[]'::jsonb,
            system_image VARCHAR(40) NOT NULL DEFAULT 'person.3',
            creator_id UUID REFERENCES users(id) ON DELETE SET NULL,
            is_official BOOLEAN NOT NULL DEFAULT FALSE,
            status VARCHAR(16) NOT NULL DEFAULT 'active',
            member_count INTEGER NOT NULL DEFAULT 0,
            weekly_active INTEGER NOT NULL DEFAULT 0,
            conversation_id UUID,
            admin_note VARCHAR(500),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            dissolved_at TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_clubs_name_live ON clubs (lower(name)) WHERE status <> 'dissolved'")
    op.execute("CREATE INDEX IF NOT EXISTS ix_clubs_topic ON clubs (topic)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_clubs_city ON clubs (city)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_clubs_status ON clubs (status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_clubs_creator_id ON clubs (creator_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_clubs_created_at ON clubs (created_at)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS club_members (
            id UUID PRIMARY KEY,
            club_id UUID NOT NULL REFERENCES clubs(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role VARCHAR(16) NOT NULL DEFAULT 'member',
            status VARCHAR(16) NOT NULL DEFAULT 'active',
            nickname VARCHAR(32),
            joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_active_at TIMESTAMPTZ,
            CONSTRAINT uq_club_member UNIQUE (club_id, user_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_club_members_club_id ON club_members (club_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_club_members_user_id ON club_members (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_club_members_status ON club_members (status)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS guilds (
            id UUID PRIMARY KEY,
            name VARCHAR(40) NOT NULL,
            specialty VARCHAR(80) NOT NULL DEFAULT '',
            city VARCHAR(48) NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            tags JSONB NOT NULL DEFAULT '[]'::jsonb,
            system_image VARCHAR(40) NOT NULL DEFAULT 'person.2',
            price_from_cents INTEGER NOT NULL DEFAULT 0,
            owner_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'active',
            conversation_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_guilds_city ON guilds (city)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_guilds_status ON guilds (status)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS guild_follows (
            id UUID PRIMARY KEY,
            guild_id UUID NOT NULL REFERENCES guilds(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_guild_follow UNIQUE (guild_id, user_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_guild_follows_guild_id ON guild_follows (guild_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_guild_follows_user_id ON guild_follows (user_id)")
    op.execute("ALTER TABLE companion_profiles ADD COLUMN IF NOT EXISTS guild_id UUID")
    op.execute("CREATE INDEX IF NOT EXISTS ix_companion_profiles_guild_id ON companion_profiles (guild_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_companion_profiles_guild_id")
    op.execute("ALTER TABLE companion_profiles DROP COLUMN IF EXISTS guild_id")
    op.execute("DROP TABLE IF EXISTS guild_follows")
    op.execute("DROP TABLE IF EXISTS guilds")
    op.execute("DROP TABLE IF EXISTS club_members")
    op.execute("DROP TABLE IF EXISTS clubs")
