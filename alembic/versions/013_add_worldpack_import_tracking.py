"""Add worldpack import tracking columns

Revision ID: 013
Revises: 012
Create Date: 2026-02-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("world_entities") as batch_op:
        batch_op.add_column(sa.Column("worldpack_pack_id", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("worldpack_key", sa.String(length=255), nullable=True))
        batch_op.create_unique_constraint(
            "uq_world_entities_novel_worldpack_pack_key",
            ["novel_id", "worldpack_pack_id", "worldpack_key"],
        )
        batch_op.create_check_constraint(
            "ck_world_entities_worldpack_identity_complete",
            "(worldpack_pack_id IS NULL AND worldpack_key IS NULL) OR "
            "(worldpack_pack_id IS NOT NULL AND worldpack_key IS NOT NULL)",
        )

    with op.batch_alter_table("world_relationships") as batch_op:
        batch_op.add_column(sa.Column("worldpack_pack_id", sa.String(length=255), nullable=True))

    with op.batch_alter_table("world_entity_attributes") as batch_op:
        batch_op.add_column(
            sa.Column(
                "origin",
                sa.String(length=20),
                nullable=False,
                server_default="manual",
            )
        )
        batch_op.add_column(sa.Column("worldpack_pack_id", sa.String(length=255), nullable=True))

    with op.batch_alter_table("world_systems") as batch_op:
        batch_op.add_column(
            sa.Column(
                "origin",
                sa.String(length=20),
                nullable=False,
                server_default="manual",
            )
        )
        batch_op.add_column(sa.Column("worldpack_pack_id", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("world_systems") as batch_op:
        batch_op.drop_column("worldpack_pack_id")
        batch_op.drop_column("origin")

    with op.batch_alter_table("world_entity_attributes") as batch_op:
        batch_op.drop_column("worldpack_pack_id")
        batch_op.drop_column("origin")

    with op.batch_alter_table("world_relationships") as batch_op:
        batch_op.drop_column("worldpack_pack_id")

    with op.batch_alter_table("world_entities") as batch_op:
        batch_op.drop_constraint("uq_world_entities_novel_worldpack_pack_key", type_="unique")
        batch_op.drop_constraint("ck_world_entities_worldpack_identity_complete", type_="check")
        batch_op.drop_column("worldpack_key")
        batch_op.drop_column("worldpack_pack_id")
