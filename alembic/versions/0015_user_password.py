"""B-class: app account password hash

Revision ID: 0015_user_password
Revises: 0014_b_class_apis
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015_user_password"
down_revision: Union[str, None] = "0014_b_class_apis"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "password_hash")
