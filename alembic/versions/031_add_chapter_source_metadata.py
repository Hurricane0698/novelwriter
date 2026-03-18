"""Add chapter source metadata for future imports without rewriting history.

Deletion notes:
- Removes the legacy contract where new imported chapter headings were stored
  only in `chapters.title`, forcing UI/search code to guess whether a title
  contained a raw source label or a user-edited title.
- Keeps existing `chapters.title` values untouched during migration because
  historical rows do not carry trustworthy import provenance.

Rollback:
- `alembic downgrade 030`
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "031"
down_revision: Union[str, None] = "030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("chapters")}

    with op.batch_alter_table("chapters") as batch_op:
        if "source_chapter_label" not in columns:
            batch_op.add_column(sa.Column("source_chapter_label", sa.String(length=255), nullable=True))
        if "source_chapter_number" not in columns:
            batch_op.add_column(sa.Column("source_chapter_number", sa.Integer(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("chapters")}

    with op.batch_alter_table("chapters") as batch_op:
        if "source_chapter_number" in columns:
            batch_op.drop_column("source_chapter_number")
        if "source_chapter_label" in columns:
            batch_op.drop_column("source_chapter_label")
