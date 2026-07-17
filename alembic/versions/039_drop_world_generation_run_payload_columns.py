"""Drop write-only world_generation_runs columns.

Deletion notes:
- `world_generation_runs.request_hash` and `response_payload` were written on
  every run but never read back: duplicate-click admission keys on
  `(user_id, novel_id, status='running')`, and the generation response is
  returned inline rather than served from the run row.
- The run row remains the durable admission/audit record (status, error_code,
  error_message, completed_at).

Rollback:
- `alembic downgrade 038` restores the columns empty (`request_hash` comes
  back nullable; historical values are not restored)
- `git revert <commit>`
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "039"
down_revision: Union[str, None] = "038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "world_generation_runs"


def _existing_columns(bind) -> set[str]:
    inspector = sa.inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return set()
    return {column["name"] for column in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    columns = _existing_columns(op.get_bind())
    if "request_hash" in columns:
        op.drop_column(_TABLE, "request_hash")
    if "response_payload" in columns:
        op.drop_column(_TABLE, "response_payload")


def downgrade() -> None:
    columns = _existing_columns(op.get_bind())
    if columns and "request_hash" not in columns:
        op.add_column(_TABLE, sa.Column("request_hash", sa.String(length=64), nullable=True))
    if columns and "response_payload" not in columns:
        op.add_column(_TABLE, sa.Column("response_payload", sa.JSON(), nullable=True))
