"""Keep a candidate's current draft and current world-value sources.

No review table, text history, or fact ledger is introduced.
"""

from alembic import op
import sqlalchemy as sa

revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None

WORLD_TABLES = (
    "world_entities",
    "world_entity_attributes",
    "world_relationships",
    "world_systems",
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table, column in [
        ("continuations", sa.Column("edited_content", sa.Text(), nullable=True)),
        *[
            (name, sa.Column("source_metadata", sa.JSON(), nullable=True))
            for name in WORLD_TABLES
        ],
    ]:
        if column.name not in {item["name"] for item in inspector.get_columns(table)}:
            op.add_column(table, column)


def downgrade() -> None:
    for table in WORLD_TABLES:
        op.drop_column(table, "source_metadata")
    op.drop_column("continuations", "edited_content")
