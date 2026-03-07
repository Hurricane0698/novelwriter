"""Add preferences JSON column to users table

Revision ID: 019
Revises: 0980e97db862
Create Date: 2026-03-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '019'
down_revision: Union[str, None] = '0980e97db862'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('preferences', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'preferences')
