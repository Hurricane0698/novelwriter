"""Add plot hierarchy tables (arc, thread, beat)

Revision ID: 003
Revises: 002
Create Date: 2025-12-23

Phase 3.1: Plot Hierarchy Data Models
- PlotArc: High-level plot arc spanning ~100 chapters
- PlotThread: Plot thread with forward-looking directives (next_beats, foreshadowing)
- PlotBeat: Per-scene plot beat tracking
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create plot_arcs table
    op.create_table(
        'plot_arcs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('novel_id', sa.Integer(), nullable=False),
        sa.Column('arc_name', sa.String(255), nullable=False),
        sa.Column('chapter_start', sa.Integer(), nullable=False),
        sa.Column('chapter_end', sa.Integer(), nullable=False),
        sa.Column('arc_type', sa.String(50), nullable=True),
        sa.Column('central_conflict', sa.Text(), nullable=True),
        sa.Column('tone', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['novel_id'], ['novels.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create index for plot_arcs
    op.create_index('ix_plot_arcs_novel_chapters', 'plot_arcs', ['novel_id', 'chapter_start', 'chapter_end'])

    # Create plot_threads table
    op.create_table(
        'plot_threads',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('arc_id', sa.Integer(), nullable=False),
        sa.Column('thread_name', sa.String(255), nullable=False),
        sa.Column('chapter_start', sa.Integer(), nullable=False),
        sa.Column('chapter_end', sa.Integer(), nullable=True),  # NULL = ongoing
        sa.Column('thread_type', sa.String(50), nullable=True),
        sa.Column('status', sa.String(30), nullable=False, server_default='active'),
        sa.Column('tension_level', sa.Integer(), nullable=False, server_default='50'),
        sa.Column('next_beats', sa.Text(), nullable=True),
        sa.Column('foreshadowing_planted', sa.Text(), nullable=True),
        sa.Column('foreshadowing_payoff_by', sa.Integer(), nullable=True),
        sa.Column('resolution_conditions', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['arc_id'], ['plot_arcs.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for plot_threads
    op.create_index('ix_plot_threads_arc_chapters', 'plot_threads', ['arc_id', 'chapter_start', 'chapter_end'])
    op.create_index('ix_plot_threads_arc_status', 'plot_threads', ['arc_id', 'status'])

    # Create plot_beats table
    op.create_table(
        'plot_beats',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('thread_id', sa.Integer(), nullable=False),
        sa.Column('chapter_number', sa.Integer(), nullable=False),
        sa.Column('scene_number', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('beat_type', sa.String(50), nullable=False),
        sa.Column('coupling_mode', sa.String(30), nullable=True),
        sa.Column('advances_thread', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('consequences', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['thread_id'], ['plot_threads.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create index for plot_beats
    op.create_index('ix_plot_beats_thread_chapter_scene', 'plot_beats', ['thread_id', 'chapter_number', 'scene_number'])


def downgrade() -> None:
    # Drop plot_beats first (depends on plot_threads)
    op.drop_index('ix_plot_beats_thread_chapter_scene', table_name='plot_beats')
    op.drop_table('plot_beats')

    # Drop plot_threads (depends on plot_arcs)
    op.drop_index('ix_plot_threads_arc_status', table_name='plot_threads')
    op.drop_index('ix_plot_threads_arc_chapters', table_name='plot_threads')
    op.drop_table('plot_threads')

    # Drop plot_arcs
    op.drop_index('ix_plot_arcs_novel_chapters', table_name='plot_arcs')
    op.drop_table('plot_arcs')
