"""Add the native Markdown source contract.

Deletion notes:
- Removes the single-format assumption from novels and ingest jobs.
- Existing novels are explicitly classified as plain text; no format guessing
  is retained for historical rows.

Rollback:
- ``alembic downgrade 040`` removes format, volume, and ingest error-code
  metadata. Chapter bodies remain intact.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "041"
down_revision: Union[str, None] = "040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOVELS_TABLE = "novels"
_CHAPTERS_TABLE = "chapters"
_NOVEL_INGEST_JOBS_TABLE = "novel_ingest_jobs"
_CONTENT_FORMAT_COLUMN = "content_format"
_SOURCE_VOLUME_TITLE_COLUMN = "source_volume_title"
_INGEST_ERROR_CODE_COLUMN = "error_code"
_CONTENT_FORMAT_CONSTRAINT = "ck_novels_content_format"
_INGEST_ERROR_CODE_CONSTRAINT = "ck_novel_ingest_jobs_error_code"


def _columns(bind, table_name: str) -> dict[str, dict]:
    return {
        column["name"]: column
        for column in sa.inspect(bind).get_columns(table_name)
    }


def _check_constraint_names(bind, table_name: str) -> set[str]:
    return {
        constraint["name"]
        for constraint in sa.inspect(bind).get_check_constraints(table_name)
        if constraint["name"] is not None
    }


def _ensure_novel_content_format(bind) -> None:
    columns = _columns(bind, _NOVELS_TABLE)
    if _CONTENT_FORMAT_COLUMN not in columns:
        with op.batch_alter_table(_NOVELS_TABLE) as batch_op:
            batch_op.add_column(
                sa.Column(
                    _CONTENT_FORMAT_COLUMN,
                    sa.String(length=20),
                    nullable=False,
                    server_default="plain_text",
                )
            )

    op.execute(
        "UPDATE novels SET content_format = 'plain_text' "
        "WHERE content_format IS NULL"
    )

    content_format = _columns(bind, _NOVELS_TABLE)[_CONTENT_FORMAT_COLUMN]
    constraint_missing = (
        _CONTENT_FORMAT_CONSTRAINT
        not in _check_constraint_names(bind, _NOVELS_TABLE)
    )
    column_contract_missing = (
        content_format["nullable"] or content_format["default"] is not None
    )
    if constraint_missing or column_contract_missing:
        with op.batch_alter_table(_NOVELS_TABLE) as batch_op:
            if constraint_missing:
                batch_op.create_check_constraint(
                    _CONTENT_FORMAT_CONSTRAINT,
                    "content_format IN ('plain_text', 'markdown')",
                )
            if column_contract_missing:
                batch_op.alter_column(
                    _CONTENT_FORMAT_COLUMN,
                    existing_type=sa.String(length=20),
                    nullable=False,
                    server_default=None,
                )


def _ensure_chapter_source_volume_title(bind) -> None:
    if _SOURCE_VOLUME_TITLE_COLUMN in _columns(bind, _CHAPTERS_TABLE):
        return

    with op.batch_alter_table(_CHAPTERS_TABLE) as batch_op:
        batch_op.add_column(
            sa.Column(
                _SOURCE_VOLUME_TITLE_COLUMN,
                sa.String(length=255),
                nullable=True,
            )
        )


def _ensure_ingest_error_code(bind) -> None:
    if _INGEST_ERROR_CODE_COLUMN not in _columns(bind, _NOVEL_INGEST_JOBS_TABLE):
        with op.batch_alter_table(_NOVEL_INGEST_JOBS_TABLE) as batch_op:
            batch_op.add_column(
                sa.Column(_INGEST_ERROR_CODE_COLUMN, sa.String(length=64), nullable=True)
            )

    op.execute(
        "UPDATE novel_ingest_jobs SET error_code = 'ingest_internal_error' "
        "WHERE status = 'failed' AND error_code IS NULL"
    )

    if (
        _INGEST_ERROR_CODE_CONSTRAINT
        in _check_constraint_names(bind, _NOVEL_INGEST_JOBS_TABLE)
    ):
        return

    with op.batch_alter_table(_NOVEL_INGEST_JOBS_TABLE) as batch_op:
        batch_op.create_check_constraint(
            _INGEST_ERROR_CODE_CONSTRAINT,
            "error_code IS NULL OR error_code IN "
            "('source_missing', 'source_encoding_unsupported', "
            "'markdown_structure_invalid', 'ingest_internal_error')",
        )


def upgrade() -> None:
    bind = op.get_bind()
    _ensure_novel_content_format(bind)
    _ensure_chapter_source_volume_title(bind)
    _ensure_ingest_error_code(bind)


def downgrade() -> None:
    with op.batch_alter_table("novel_ingest_jobs") as batch_op:
        batch_op.drop_constraint("ck_novel_ingest_jobs_error_code", type_="check")
        batch_op.drop_column("error_code")

    with op.batch_alter_table("chapters") as batch_op:
        batch_op.drop_column("source_volume_title")

    with op.batch_alter_table("novels") as batch_op:
        batch_op.drop_constraint("ck_novels_content_format", type_="check")
        batch_op.drop_column("content_format")
