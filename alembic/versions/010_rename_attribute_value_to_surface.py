"""Rename world_entity_attributes.value → surface, drop unresolved visibility

Revision ID: 010
Revises: 009
Create Date: 2026-02-13
"""
from typing import Sequence, Union

from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("world_entity_attributes") as batch_op:
        batch_op.alter_column("value", new_column_name="surface")
    # Migrate any 'unresolved' visibility to 'active'
    op.execute("UPDATE world_entity_attributes SET visibility = 'active' WHERE visibility = 'unresolved'")
    op.execute("UPDATE world_relationships SET visibility = 'active' WHERE visibility = 'unresolved'")
    op.execute("UPDATE world_systems SET visibility = 'active' WHERE visibility = 'unresolved'")


def downgrade() -> None:
    op.execute("UPDATE world_entity_attributes SET visibility = 'unresolved' WHERE visibility = 'active' AND truth IS NOT NULL")
    with op.batch_alter_table("world_entity_attributes") as batch_op:
        batch_op.alter_column("surface", new_column_name="value")
