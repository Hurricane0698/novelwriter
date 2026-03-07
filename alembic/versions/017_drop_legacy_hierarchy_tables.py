"""Drop legacy narrative/character/plot hierarchy tables.

Revision ID: 017
Revises: 016
Create Date: 2026-03-04

Deletion notes (pre-launch requirement):
- Drops legacy tables that are no longer part of the product architecture:
  - narrative_events, narrative_facts, narrative_styles
  - character_arcs, character_epochs, character_moments
  - plot_arcs, plot_threads, plot_beats
- This is destructive: all rows in these tables are permanently deleted.

Rollback path (pre-launch requirement):
- Preferred: `git revert <commit>`
- Structural rollback: `alembic downgrade 016` recreates the empty legacy tables
  (data is not restored).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_table_if_exists(table: str) -> None:
    # Alembic's op.drop_table doesn't support `if_exists` in all versions.
    # Use dialect-neutral raw SQL instead.
    op.execute(sa.text(f"DROP TABLE IF EXISTS {table}"))


def upgrade() -> None:
    # Drop in dependency order (children first).
    for table in [
        # Character hierarchy: moments -> epochs -> arcs.
        "character_moments",
        "character_epochs",
        "character_arcs",
        # Plot hierarchy: beats -> threads -> arcs.
        "plot_beats",
        "plot_threads",
        "plot_arcs",
        # Narrative tables (character_epochs referenced narrative_events).
        "narrative_styles",
        "narrative_facts",
        "narrative_events",
    ]:
        _drop_table_if_exists(table)


def downgrade() -> None:
    # Recreate tables as they existed at revision 016 (schema-only; no data restore).
    #
    # NOTE: narrative_events had an additional coupling_mode column added in revision 005,
    # which is part of the schema at 016.

    # narrative_events
    op.create_table(
        "narrative_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("novel_id", sa.Integer(), nullable=False),
        sa.Column("chapter_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("cause_event_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("source", sa.String(30), nullable=False, server_default="user_created"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("coupling_mode", sa.String(length=30), nullable=True),
        sa.ForeignKeyConstraint(["novel_id"], ["novels.id"]),
        sa.ForeignKeyConstraint(
            ["cause_event_id", "novel_id"],
            ["narrative_events.id", "narrative_events.novel_id"],
            name="fk_narrative_events_cause_event",
        ),
        sa.UniqueConstraint("id", "novel_id", name="uq_narrative_events_id_novel"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_narrative_events_novel_chapter",
        "narrative_events",
        ["novel_id", "chapter_number"],
    )
    op.create_index(
        "ix_narrative_events_novel_subject",
        "narrative_events",
        ["novel_id", "subject"],
    )

    # narrative_facts
    op.create_table(
        "narrative_facts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("novel_id", sa.Integer(), nullable=False),
        sa.Column("chapter_number", sa.Integer(), nullable=False),
        sa.Column("fact_type", sa.String(50), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("user_override", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column("source", sa.String(30), nullable=False, server_default="user_created"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["novel_id"], ["novels.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_narrative_facts_novel_chapter",
        "narrative_facts",
        ["novel_id", "chapter_number"],
    )
    op.create_index(
        "ix_narrative_facts_novel_subject",
        "narrative_facts",
        ["novel_id", "subject"],
    )

    # narrative_styles
    op.create_table(
        "narrative_styles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("novel_id", sa.Integer(), nullable=False),
        sa.Column("chapter_start", sa.Integer(), nullable=False),
        sa.Column("chapter_end", sa.Integer(), nullable=False),
        sa.Column("prose_style", sa.Text(), nullable=True),
        sa.Column("tone", sa.Text(), nullable=True),
        sa.Column("pacing", sa.Text(), nullable=True),
        sa.Column("sample_passages", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["novel_id"], ["novels.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_narrative_styles_novel_chapters",
        "narrative_styles",
        ["novel_id", "chapter_start", "chapter_end"],
    )

    # character_arcs
    op.create_table(
        "character_arcs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("novel_id", sa.Integer(), nullable=False),
        sa.Column("character_name", sa.String(255), nullable=False),
        sa.Column("chapter_start", sa.Integer(), nullable=False),
        sa.Column("chapter_end", sa.Integer(), nullable=False),
        sa.Column("base_personality", sa.Text(), nullable=True),
        sa.Column("arc_trajectory", sa.Text(), nullable=True),
        sa.Column("narrative_voice", sa.Text(), nullable=True),
        sa.Column("style_evolution", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["novel_id"], ["novels.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_character_arcs_novel_character",
        "character_arcs",
        ["novel_id", "character_name"],
    )
    op.create_index(
        "ix_character_arcs_novel_chapters",
        "character_arcs",
        ["novel_id", "chapter_start", "chapter_end"],
    )

    # character_epochs
    op.create_table(
        "character_epochs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("arc_id", sa.Integer(), nullable=False),
        sa.Column("chapter_start", sa.Integer(), nullable=False),
        sa.Column("chapter_end", sa.Integer(), nullable=False),
        sa.Column("active_personality", sa.Text(), nullable=True),
        sa.Column("emotional_baseline", sa.Text(), nullable=True),
        sa.Column("current_goals", sa.Text(), nullable=True),
        sa.Column("style_tone", sa.Text(), nullable=True),
        sa.Column("triggered_by_event_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["arc_id"], ["character_arcs.id"]),
        sa.ForeignKeyConstraint(["triggered_by_event_id"], ["narrative_events.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_character_epochs_arc_chapters",
        "character_epochs",
        ["arc_id", "chapter_start", "chapter_end"],
    )

    # character_moments
    op.create_table(
        "character_moments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("epoch_id", sa.Integer(), nullable=False),
        sa.Column("chapter_number", sa.Integer(), nullable=False),
        sa.Column("scene_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("emotional_state", sa.Text(), nullable=True),
        sa.Column("immediate_intent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["epoch_id"], ["character_epochs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_character_moments_epoch_chapter_scene",
        "character_moments",
        ["epoch_id", "chapter_number", "scene_number"],
    )

    # plot_arcs
    op.create_table(
        "plot_arcs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("novel_id", sa.Integer(), nullable=False),
        sa.Column("arc_name", sa.String(255), nullable=False),
        sa.Column("chapter_start", sa.Integer(), nullable=False),
        sa.Column("chapter_end", sa.Integer(), nullable=False),
        sa.Column("arc_type", sa.String(50), nullable=True),
        sa.Column("central_conflict", sa.Text(), nullable=True),
        sa.Column("tone", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["novel_id"], ["novels.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_plot_arcs_novel_chapters",
        "plot_arcs",
        ["novel_id", "chapter_start", "chapter_end"],
    )

    # plot_threads
    op.create_table(
        "plot_threads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("arc_id", sa.Integer(), nullable=False),
        sa.Column("thread_name", sa.String(255), nullable=False),
        sa.Column("chapter_start", sa.Integer(), nullable=False),
        sa.Column("chapter_end", sa.Integer(), nullable=True),
        sa.Column("thread_type", sa.String(50), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("tension_level", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("next_beats", sa.Text(), nullable=True),
        sa.Column("foreshadowing_planted", sa.Text(), nullable=True),
        sa.Column("foreshadowing_payoff_by", sa.Integer(), nullable=True),
        sa.Column("resolution_conditions", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["arc_id"], ["plot_arcs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_plot_threads_arc_chapters",
        "plot_threads",
        ["arc_id", "chapter_start", "chapter_end"],
    )
    op.create_index(
        "ix_plot_threads_arc_status",
        "plot_threads",
        ["arc_id", "status"],
    )

    # plot_beats
    op.create_table(
        "plot_beats",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("thread_id", sa.Integer(), nullable=False),
        sa.Column("chapter_number", sa.Integer(), nullable=False),
        sa.Column("scene_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("beat_type", sa.String(50), nullable=False),
        sa.Column("coupling_mode", sa.String(30), nullable=True),
        sa.Column("advances_thread", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("consequences", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["thread_id"], ["plot_threads.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_plot_beats_thread_chapter_scene",
        "plot_beats",
        ["thread_id", "chapter_number", "scene_number"],
    )
