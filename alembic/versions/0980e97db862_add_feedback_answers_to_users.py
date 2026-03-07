"""add_feedback_answers_to_users

Revision ID: 0980e97db862
Revises: 018
Create Date: 2026-03-05 15:21:02.159822

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0980e97db862'
down_revision: Union[str, None] = '018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('feedback_answers', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'feedback_answers')
