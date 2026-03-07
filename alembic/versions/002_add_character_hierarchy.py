"""Add character hierarchy tables (arc, epoch, moment)

Revision ID: 002
Revises: 001
Create Date: 2025-12-22

Phase 2.1: Character Hierarchy Data Models
- CharacterArc: High-level arc spanning ~100 chapters
- CharacterEpoch: Medium-term state spanning 10-20 chapters
- CharacterMoment: Per-scene character state
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create character_arcs table
    op.create_table(
        'character_arcs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('novel_id', sa.Integer(), nullable=False),
        sa.Column('character_name', sa.String(255), nullable=False),
        sa.Column('chapter_start', sa.Integer(), nullable=False),
        sa.Column('chapter_end', sa.Integer(), nullable=False),
        sa.Column('base_personality', sa.Text(), nullable=True),
        sa.Column('arc_trajectory', sa.Text(), nullable=True),
        sa.Column('narrative_voice', sa.Text(), nullable=True),
        sa.Column('style_evolution', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['novel_id'], ['novels.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for character_arcs
    op.create_index('ix_character_arcs_novel_character', 'character_arcs', ['novel_id', 'character_name'])
    op.create_index('ix_character_arcs_novel_chapters', 'character_arcs', ['novel_id', 'chapter_start', 'chapter_end'])

    # Create character_epochs table
    op.create_table(
        'character_epochs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('arc_id', sa.Integer(), nullable=False),
        sa.Column('chapter_start', sa.Integer(), nullable=False),
        sa.Column('chapter_end', sa.Integer(), nullable=False),
        sa.Column('active_personality', sa.Text(), nullable=True),
        sa.Column('emotional_baseline', sa.Text(), nullable=True),
        sa.Column('current_goals', sa.Text(), nullable=True),
        sa.Column('style_tone', sa.Text(), nullable=True),
        sa.Column('triggered_by_event_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['arc_id'], ['character_arcs.id'], ),
        sa.ForeignKeyConstraint(['triggered_by_event_id'], ['narrative_events.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create index for character_epochs
    op.create_index('ix_character_epochs_arc_chapters', 'character_epochs', ['arc_id', 'chapter_start', 'chapter_end'])

    # Create character_moments table
    op.create_table(
        'character_moments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('epoch_id', sa.Integer(), nullable=False),
        sa.Column('chapter_number', sa.Integer(), nullable=False),
        sa.Column('scene_number', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('emotional_state', sa.Text(), nullable=True),
        sa.Column('immediate_intent', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['epoch_id'], ['character_epochs.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create index for character_moments
    op.create_index('ix_character_moments_epoch_chapter_scene', 'character_moments', ['epoch_id', 'chapter_number', 'scene_number'])


def downgrade() -> None:
    # Drop character_moments first (depends on character_epochs)
    op.drop_index('ix_character_moments_epoch_chapter_scene', table_name='character_moments')
    op.drop_table('character_moments')

    # Drop character_epochs (depends on character_arcs)
    op.drop_index('ix_character_epochs_arc_chapters', table_name='character_epochs')
    op.drop_table('character_epochs')

    # Drop character_arcs
    op.drop_index('ix_character_arcs_novel_chapters', table_name='character_arcs')
    op.drop_index('ix_character_arcs_novel_character', table_name='character_arcs')
    op.drop_table('character_arcs')
