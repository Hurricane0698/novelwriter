"""Repair generation admission tables skipped by legacy selfhost stamping.

Deletion notes:
- Removes the invalid v0.3.2 selfhost state where Alembic could be stamped past
  revision 034 while ``continuation_runs`` was still absent.
- Restores the canonical durable admission tables used by continuation and
  world generation; request handlers do not create or repair schema at runtime.

Rollback:
- ``alembic downgrade 039`` is a no-op because healthy revision 039 databases
  already contain these tables. Reverting the application commit removes the
  repair migration without deleting recovered run history.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "040"
down_revision: Union[str, None] = "039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CONTINUATION_TABLE = "continuation_runs"
_WORLD_GENERATION_TABLE = "world_generation_runs"


def _table_names(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _column_names(bind, table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def _index_names(bind, table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(bind).get_indexes(table_name)}


def _create_continuation_runs() -> None:
    op.create_table(
        _CONTINUATION_TABLE,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("novel_id", sa.Integer(), nullable=False),
        sa.Column("client_request_id", sa.String(length=64), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("semantic_key", sa.String(length=64), nullable=True),
        sa.Column("claim_token", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("delivered_count", sa.Integer(), nullable=False),
        sa.Column("continuation_ids", sa.JSON(), nullable=True),
        sa.Column("debug_summary", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True
        ),
        sa.ForeignKeyConstraint(["novel_id"], ["novels.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "novel_id",
            "client_request_id",
            name="uq_continuation_runs_user_novel_request",
        ),
    )


def _ensure_continuation_runs(bind) -> None:
    if _CONTINUATION_TABLE not in _table_names(bind):
        _create_continuation_runs()
    else:
        columns = _column_names(bind, _CONTINUATION_TABLE)
        if "semantic_key" not in columns:
            with op.batch_alter_table(_CONTINUATION_TABLE) as batch_op:
                batch_op.add_column(
                    sa.Column("semantic_key", sa.String(length=64), nullable=True)
                )

    indexes = _index_names(bind, _CONTINUATION_TABLE)
    if "ix_continuation_runs_novel_status" not in indexes:
        op.create_index(
            "ix_continuation_runs_novel_status",
            _CONTINUATION_TABLE,
            ["novel_id", "status"],
        )
    if "uq_continuation_runs_active_semantic" not in indexes:
        op.create_index(
            "uq_continuation_runs_active_semantic",
            _CONTINUATION_TABLE,
            ["user_id", "novel_id", "semantic_key"],
            unique=True,
            sqlite_where=sa.text("semantic_key IS NOT NULL AND status = 'running'"),
            postgresql_where=sa.text("semantic_key IS NOT NULL AND status = 'running'"),
        )


def _create_world_generation_runs() -> None:
    op.create_table(
        _WORLD_GENERATION_TABLE,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("novel_id", sa.Integer(), nullable=False),
        sa.Column("claim_token", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True
        ),
        sa.ForeignKeyConstraint(["novel_id"], ["novels.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def _ensure_world_generation_runs(bind) -> None:
    if _WORLD_GENERATION_TABLE not in _table_names(bind):
        _create_world_generation_runs()

    indexes = _index_names(bind, _WORLD_GENERATION_TABLE)
    if "ix_world_generation_runs_novel_status" not in indexes:
        op.create_index(
            "ix_world_generation_runs_novel_status",
            _WORLD_GENERATION_TABLE,
            ["novel_id", "status"],
        )
    if "uq_world_generation_runs_active_user_novel" not in indexes:
        op.create_index(
            "uq_world_generation_runs_active_user_novel",
            _WORLD_GENERATION_TABLE,
            ["user_id", "novel_id"],
            unique=True,
            sqlite_where=sa.text("status = 'running'"),
            postgresql_where=sa.text("status = 'running'"),
        )


def upgrade() -> None:
    bind = op.get_bind()
    _ensure_continuation_runs(bind)
    _ensure_world_generation_runs(bind)


def downgrade() -> None:
    pass
