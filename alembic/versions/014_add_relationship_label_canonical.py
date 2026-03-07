"""Add label_canonical to world_relationships

Revision ID: 014
Revises: 013
Create Date: 2026-03-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.world_relationships import canonicalize_relationship_label


# revision identifiers, used by Alembic.
revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_LABEL_CANONICAL_INDEX = "ix_world_relationships_pair_label_canonical"


def upgrade() -> None:
    with op.batch_alter_table("world_relationships") as batch_op:
        batch_op.add_column(
            sa.Column(
                "label_canonical",
                sa.String(length=100),
                nullable=False,
                server_default="",
            )
        )

    op.create_index(
        _LABEL_CANONICAL_INDEX,
        "world_relationships",
        ["novel_id", "source_id", "target_id", "label_canonical"],
    )

    conn = op.get_bind()
    rel_table = sa.table(
        "world_relationships",
        sa.column("id", sa.Integer),
        sa.column("label", sa.String),
        sa.column("label_canonical", sa.String),
    )
    rows = conn.execute(sa.select(rel_table.c.id, rel_table.c.label)).fetchall()
    for rel_id, label in rows:
        canonical = canonicalize_relationship_label(label or "")
        conn.execute(
            rel_table.update()
            .where(rel_table.c.id == rel_id)
            .values(label_canonical=canonical)
        )


def downgrade() -> None:
    op.drop_index(_LABEL_CANONICAL_INDEX, table_name="world_relationships")
    with op.batch_alter_table("world_relationships") as batch_op:
        batch_op.drop_column("label_canonical")
