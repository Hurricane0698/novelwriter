"""Add narrative_events and narrative_facts tables

Revision ID: 001
Revises:
Create Date: 2025-12-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create narrative_events table
    op.create_table(
        'narrative_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('novel_id', sa.Integer(), nullable=False),
        sa.Column('chapter_number', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('subject', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('old_value', sa.Text(), nullable=True),
        sa.Column('new_value', sa.Text(), nullable=True),
        sa.Column('cause_event_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='draft'),
        sa.Column('source', sa.String(30), nullable=False, server_default='user_created'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['novel_id'], ['novels.id'], ),
        sa.ForeignKeyConstraint(
            ['cause_event_id', 'novel_id'],
            ['narrative_events.id', 'narrative_events.novel_id'],
            name='fk_narrative_events_cause_event',
        ),
        sa.UniqueConstraint('id', 'novel_id', name='uq_narrative_events_id_novel'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for narrative_events
    op.create_index('ix_narrative_events_novel_chapter', 'narrative_events', ['novel_id', 'chapter_number'])
    op.create_index('ix_narrative_events_novel_subject', 'narrative_events', ['novel_id', 'subject'])

    # Create narrative_facts table
    op.create_table(
        'narrative_facts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('novel_id', sa.Integer(), nullable=False),
        sa.Column('chapter_number', sa.Integer(), nullable=False),
        sa.Column('fact_type', sa.String(50), nullable=False),
        sa.Column('subject', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('user_override', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('override_reason', sa.Text(), nullable=True),
        sa.Column('source', sa.String(30), nullable=False, server_default='user_created'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['novel_id'], ['novels.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for narrative_facts
    op.create_index('ix_narrative_facts_novel_chapter', 'narrative_facts', ['novel_id', 'chapter_number'])
    op.create_index('ix_narrative_facts_novel_subject', 'narrative_facts', ['novel_id', 'subject'])


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('ix_narrative_facts_novel_subject', table_name='narrative_facts')
    op.drop_index('ix_narrative_facts_novel_chapter', table_name='narrative_facts')
    op.drop_table('narrative_facts')

    op.drop_index('ix_narrative_events_novel_subject', table_name='narrative_events')
    op.drop_index('ix_narrative_events_novel_chapter', table_name='narrative_events')
    op.drop_table('narrative_events')
