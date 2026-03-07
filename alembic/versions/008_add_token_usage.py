"""Add token_usage table

Revision ID: 008
Revises: 007
Create Date: 2026-02-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "token_usage",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_estimate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("endpoint", sa.String(255), nullable=True),
        sa.Column("node_name", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_token_usage_created_at", "token_usage", ["created_at"])
    op.create_index("ix_token_usage_model", "token_usage", ["model"])


def downgrade() -> None:
    op.drop_index("ix_token_usage_model", table_name="token_usage")
    op.drop_index("ix_token_usage_created_at", table_name="token_usage")
    op.drop_table("token_usage")
