"""Add token_usage (user_id, created_at) index

Revision ID: 015
Revises: d12374b717eb
Create Date: 2026-03-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "015"
down_revision: Union[str, None] = "d12374b717eb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_INDEX_NAME = "ix_token_usage_user_id_created_at"


def _has_index(bind) -> bool:
    try:
        inspector = sa.inspect(bind)
        indexes = inspector.get_indexes("token_usage")
    except Exception:
        return False
    return any((idx.get("name") or "") == _INDEX_NAME for idx in indexes)


def upgrade() -> None:
    bind = op.get_bind()
    dialect = getattr(getattr(bind, "dialect", None), "name", "") if bind is not None else ""

    # Prefer dialect-native IF NOT EXISTS where available so introspection failures
    # can't cause hard migration failures on repeated deploys.
    if dialect in {"postgresql", "sqlite"}:
        op.execute(
            sa.text(
                f"CREATE INDEX IF NOT EXISTS {_INDEX_NAME} "
                "ON token_usage (user_id, created_at)"
            )
        )
        return

    if bind is not None and _has_index(bind):
        return

    try:
        op.create_index(_INDEX_NAME, "token_usage", ["user_id", "created_at"])
    except Exception as exc:
        # Best-effort idempotency for non-SQLite/PG dialects.
        msg = str(exc).lower()
        if "already exists" in msg or "duplicate" in msg:
            return
        raise


def downgrade() -> None:
    bind = op.get_bind()
    dialect = getattr(getattr(bind, "dialect", None), "name", "") if bind is not None else ""

    if dialect in {"postgresql", "sqlite"}:
        op.execute(sa.text(f"DROP INDEX IF EXISTS {_INDEX_NAME}"))
        return

    # Best-effort idempotency for non-SQLite/PG dialects. Missing index should not
    # fail rollback, but unexpected errors should still surface.
    try:
        op.drop_index(_INDEX_NAME, table_name="token_usage")
    except Exception as exc:
        msg = str(exc).lower()
        if "no such index" in msg or "does not exist" in msg:
            return
        raise
