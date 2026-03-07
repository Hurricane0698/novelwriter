"""Add user_events table for product analytics

Revision ID: 020
Revises: 019
Create Date: 2026-03-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '020'
down_revision: Union[str, None] = '019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('event', sa.String(50), nullable=False),
        sa.Column('novel_id', sa.Integer(), nullable=True),
        sa.Column('meta', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_user_events_user_id', 'user_events', ['user_id'])
    op.create_index('ix_user_events_event', 'user_events', ['event'])
    op.create_index('ix_user_events_created_at', 'user_events', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_user_events_created_at', table_name='user_events')
    op.drop_index('ix_user_events_event', table_name='user_events')
    op.drop_index('ix_user_events_user_id', table_name='user_events')
    op.drop_table('user_events')
