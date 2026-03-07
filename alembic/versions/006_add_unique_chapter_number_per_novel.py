"""Add unique chapter number per novel

Revision ID: 006
Revises: 005
Create Date: 2026-02-04
"""
from typing import Sequence, Union

from alembic import context, op


# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove duplicate chapter rows before enforcing uniqueness.
    op.execute(
        """
        DELETE FROM chapters
        WHERE id NOT IN (
            SELECT MAX(id) FROM chapters GROUP BY novel_id, chapter_number
        )
        """
    )

    if context.get_context().dialect.name == "sqlite":
        with op.batch_alter_table("chapters") as batch_op:
            batch_op.create_unique_constraint(
                "uq_chapters_novel_chapter_number",
                ["novel_id", "chapter_number"],
            )
    else:
        op.create_unique_constraint(
            "uq_chapters_novel_chapter_number",
            "chapters",
            ["novel_id", "chapter_number"],
        )


def downgrade() -> None:
    if context.get_context().dialect.name == "sqlite":
        with op.batch_alter_table("chapters") as batch_op:
            batch_op.drop_constraint(
                "uq_chapters_novel_chapter_number",
                type_="unique",
            )
    else:
        op.drop_constraint(
            "uq_chapters_novel_chapter_number",
            "chapters",
            type_="unique",
        )
