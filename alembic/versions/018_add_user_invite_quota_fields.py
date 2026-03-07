"""Add invite/quota fields to users table

Revision ID: 018
Revises: 017
Create Date: 2026-03-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '018'
down_revision: Union[str, None] = '017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('nickname', sa.String(150), nullable=True))
    op.add_column('users', sa.Column('generation_quota', sa.Integer(), nullable=False, server_default=sa.text('5')))
    op.add_column('users', sa.Column('feedback_submitted', sa.Boolean(), nullable=False, server_default=sa.text('0')))


def downgrade() -> None:
    op.drop_column('users', 'feedback_submitted')
    op.drop_column('users', 'generation_quota')
    op.drop_column('users', 'nickname')
