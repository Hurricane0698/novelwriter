"""Add bootstrap_jobs table and novels.window_index column

Revision ID: 011
Revises: 010
Create Date: 2026-02-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("novels") as batch_op:
        batch_op.add_column(sa.Column("window_index", sa.LargeBinary(), nullable=True))

    op.create_table(
        "bootstrap_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("novel_id", sa.Integer(), sa.ForeignKey("novels.id"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("progress", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("novel_id", name="uq_bootstrap_jobs_novel_id"),
    )


def downgrade() -> None:
    op.drop_table("bootstrap_jobs")

    with op.batch_alter_table("novels") as batch_op:
        batch_op.drop_column("window_index")
