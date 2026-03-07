"""Drop deprecated story_state table (ARCH-009)

Revision ID: 009
Revises: 008
Create Date: 2026-02-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("story_state")


def downgrade() -> None:
    op.create_table(
        "story_state",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("novel_id", sa.Integer(), sa.ForeignKey("novels.id"), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("last_updated", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("novel_id", "key", name="uq_story_state_novel_key"),
    )
