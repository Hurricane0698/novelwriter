"""Add bootstrap modes and origin tracking columns

Revision ID: 012
Revises: 011
Create Date: 2026-02-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("world_entities") as batch_op:
        batch_op.add_column(
            sa.Column(
                "origin",
                sa.String(length=20),
                nullable=False,
                server_default="manual",
            )
        )

    with op.batch_alter_table("world_relationships") as batch_op:
        batch_op.add_column(
            sa.Column(
                "origin",
                sa.String(length=20),
                nullable=False,
                server_default="manual",
            )
        )

    with op.batch_alter_table("bootstrap_jobs") as batch_op:
        batch_op.add_column(
            sa.Column(
                "mode",
                sa.String(length=20),
                nullable=False,
                server_default="index_refresh",
            )
        )
        batch_op.add_column(sa.Column("draft_policy", sa.String(length=50), nullable=True))
        batch_op.add_column(
            sa.Column(
                "initialized",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    bootstrap_jobs = sa.table(
        "bootstrap_jobs",
        sa.column("status", sa.String(length=20)),
        sa.column("mode", sa.String(length=20)),
        sa.column("initialized", sa.Boolean()),
    )
    op.execute(
        bootstrap_jobs.update()
        .where(bootstrap_jobs.c.status == "completed")
        .values(mode="initial", initialized=True)
    )


def downgrade() -> None:
    with op.batch_alter_table("bootstrap_jobs") as batch_op:
        batch_op.drop_column("initialized")
        batch_op.drop_column("draft_policy")
        batch_op.drop_column("mode")

    with op.batch_alter_table("world_relationships") as batch_op:
        batch_op.drop_column("origin")

    with op.batch_alter_table("world_entities") as batch_op:
        batch_op.drop_column("origin")
