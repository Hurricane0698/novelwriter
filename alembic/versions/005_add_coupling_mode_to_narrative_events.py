"""Add coupling_mode to narrative_events

Revision ID: 005
Revises: 004
Create Date: 2026-01-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "narrative_events",
        sa.Column("coupling_mode", sa.String(length=30), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("narrative_events", "coupling_mode")
