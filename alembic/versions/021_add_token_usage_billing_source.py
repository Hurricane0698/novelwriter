"""Add billing_source to token_usage

Revision ID: 021
Revises: 020
Create Date: 2026-03-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '021'
down_revision: Union[str, None] = '020'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('token_usage') as batch_op:
        batch_op.add_column(
            sa.Column(
                'billing_source',
                sa.String(length=20),
                nullable=True,
                server_default=sa.text("'selfhost'"),
            )
        )

    op.execute("UPDATE token_usage SET billing_source = 'selfhost' WHERE billing_source IS NULL")

    with op.batch_alter_table('token_usage') as batch_op:
        batch_op.alter_column(
            'billing_source',
            existing_type=sa.String(length=20),
            nullable=False,
            server_default=None,
        )
        batch_op.create_index(
            'ix_token_usage_billing_source_created_at',
            ['billing_source', 'created_at'],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table('token_usage') as batch_op:
        batch_op.drop_index('ix_token_usage_billing_source_created_at')
        batch_op.drop_column('billing_source')
