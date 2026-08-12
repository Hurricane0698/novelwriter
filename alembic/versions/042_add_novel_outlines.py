"""Add manually ranged novel outlines.

Deletion notes:
- Replaces ad-hoc long-range continuation context with explicitly persisted,
  user-selected outline summaries.

Rollback:
- ``alembic downgrade 041`` drops generated outline rows and their index.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "042"
down_revision: Union[str, None] = "041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if "novel_outlines" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "novel_outlines",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("novel_id", sa.Integer(), nullable=False),
            sa.Column("start_chapter", sa.Integer(), nullable=False),
            sa.Column("end_chapter", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("model", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.CheckConstraint("start_chapter >= 1", name="ck_novel_outlines_start_positive"),
            sa.CheckConstraint("end_chapter >= start_chapter", name="ck_novel_outlines_range_order"),
            sa.ForeignKeyConstraint(["novel_id"], ["novels.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_novel_outlines_novel_range", "novel_outlines", ["novel_id", "start_chapter", "end_chapter"])


def downgrade() -> None:
    bind = op.get_bind()
    if "novel_outlines" in sa.inspect(bind).get_table_names():
        op.drop_index("ix_novel_outlines_novel_range", table_name="novel_outlines")
        op.drop_table("novel_outlines")
