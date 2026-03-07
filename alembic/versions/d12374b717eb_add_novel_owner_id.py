"""add novel owner_id

Revision ID: d12374b717eb
Revises: 014
Create Date: 2026-03-03 02:36:40.849191

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd12374b717eb'
down_revision: Union[str, None] = '014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else ""

    has_owner_id = False
    try:
        inspector = sa.inspect(bind)
        cols = inspector.get_columns("novels")
        has_owner_id = any(c.get("name") == "owner_id" for c in cols)
    except Exception:
        # Best-effort introspection; if this fails, let add_column attempt and raise if needed.
        has_owner_id = False

    if not has_owner_id:
        op.add_column("novels", sa.Column("owner_id", sa.Integer(), nullable=True))

    # SQLite cannot ALTER constraints; skip FK there (dev DB). Postgres can add it normally.
    if dialect != "sqlite":
        try:
            inspector = sa.inspect(bind)
            fks = inspector.get_foreign_keys("novels")
            has_fk = any((fk.get("name") or "") == "fk_novels_owner_id" for fk in fks)
        except Exception:
            has_fk = False
        if not has_fk:
            op.create_foreign_key(
                "fk_novels_owner_id",
                "novels",
                "users",
                ["owner_id"],
                ["id"],
            )

    # Assign existing novels to the first user (best-effort when user table exists).
    op.execute(
        "UPDATE novels "
        "SET owner_id = (SELECT id FROM users ORDER BY id LIMIT 1) "
        "WHERE owner_id IS NULL"
    )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else ""

    if dialect != "sqlite":
        op.drop_constraint("fk_novels_owner_id", "novels", type_="foreignkey")

    if dialect == "sqlite":
        with op.batch_alter_table("novels") as batch_op:
            batch_op.drop_column("owner_id")
    else:
        op.drop_column("novels", "owner_id")
