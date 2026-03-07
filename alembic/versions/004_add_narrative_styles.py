"""Add narrative_styles table for style evolution

Revision ID: 004
Revises: 003
Create Date: 2025-12-23

Phase 5.1: Style Evolution Data Model
- NarrativeStyle: Tracks evolving prose style per chapter range
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create narrative_styles table
    op.create_table(
        'narrative_styles',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('novel_id', sa.Integer(), nullable=False),
        sa.Column('chapter_start', sa.Integer(), nullable=False),
        sa.Column('chapter_end', sa.Integer(), nullable=False),
        sa.Column('prose_style', sa.Text(), nullable=True),
        sa.Column('tone', sa.Text(), nullable=True),
        sa.Column('pacing', sa.Text(), nullable=True),
        sa.Column('sample_passages', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['novel_id'], ['novels.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create index for narrative_styles
    op.create_index('ix_narrative_styles_novel_chapters', 'narrative_styles', ['novel_id', 'chapter_start', 'chapter_end'])


def downgrade() -> None:
    # Drop narrative_styles
    op.drop_index('ix_narrative_styles_novel_chapters', table_name='narrative_styles')
    op.drop_table('narrative_styles')
