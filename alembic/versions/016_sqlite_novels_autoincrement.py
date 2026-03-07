"""Ensure SQLite novels.id never reuses values (AUTOINCREMENT).

Why:
- SQLite `INTEGER PRIMARY KEY` may reuse the maximum deleted rowid/id.
- The frontend persists onboarding dismissal in localStorage keyed by novel identity.
  If ids are reused, client state can collide across different novels.

This migration rebuilds the `novels` table with `AUTOINCREMENT` on SQLite to make
id assignment monotonic.

Revision ID: 016
Revises: 015
Create Date: 2026-03-04
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NOVELS_TABLE_SQL = sa.text(
    "SELECT sql FROM sqlite_master WHERE type='table' AND name='novels'"
)
_NOVELS_INDEXES_SQL = sa.text(
    "SELECT sql FROM sqlite_master "
    "WHERE type='index' AND tbl_name='novels' AND sql IS NOT NULL"
)
_NOVELS_TRIGGERS_SQL = sa.text(
    "SELECT sql FROM sqlite_master "
    "WHERE type='trigger' AND tbl_name='novels' AND sql IS NOT NULL"
)


def _is_sqlite(bind) -> bool:
    return getattr(getattr(bind, "dialect", None), "name", "") == "sqlite"


def _has_autoincrement(bind) -> bool:
    row = bind.execute(_NOVELS_TABLE_SQL).fetchone()
    sql = (row[0] if row else "") or ""
    return "AUTOINCREMENT" in sql.upper()


def _get_sqlite_foreign_keys_enabled(bind) -> bool:
    row = bind.execute(sa.text("PRAGMA foreign_keys")).fetchone()
    return bool(int(row[0])) if row else False


def _set_sqlite_foreign_keys_enabled(bind, *, enabled: bool) -> None:
    bind.execute(sa.text(f"PRAGMA foreign_keys={'ON' if enabled else 'OFF'}"))


@contextmanager
def _sqlite_foreign_keys_restored(bind):
    """Temporarily disable FK enforcement and always restore previous state.

    SQLite foreign key enforcement is a per-connection PRAGMA. A mid-migration
    failure must not leave it disabled for the remainder of the migration run.
    """

    prev_enabled = _get_sqlite_foreign_keys_enabled(bind)
    _set_sqlite_foreign_keys_enabled(bind, enabled=False)
    try:
        yield
    finally:
        _set_sqlite_foreign_keys_enabled(bind, enabled=prev_enabled)


def _rebuild_novels_table(*, autoincrement: bool) -> None:
    # IMPORTANT: This migration is SQLite-only. SQLite can't ALTER TABLE to
    # add/remove AUTOINCREMENT, so we force a table rebuild.
    #
    # Reflect the current table schema and recreate it, rather than hard-coding
    # a CREATE TABLE statement (which can silently drop columns/constraints if
    # the schema drifted).
    bind = op.get_bind()
    if bind is None:
        return

    # Capture SQL-backed indexes/triggers so we can restore them after the
    # rebuild. (SQLite autoindexes created for UNIQUE constraints have NULL sql
    # and will be recreated by the table definition itself.)
    index_sql = [
        (row[0] or "")
        for row in bind.execute(_NOVELS_INDEXES_SQL).fetchall()
        if (row[0] or "").strip()
    ]
    trigger_sql = [
        (row[0] or "")
        for row in bind.execute(_NOVELS_TRIGGERS_SQL).fetchall()
        if (row[0] or "").strip()
    ]

    with _sqlite_foreign_keys_restored(bind):
        tmp_table_name = "_novels_autoinc_tmp"
        bind.exec_driver_sql(f"DROP TABLE IF EXISTS {tmp_table_name}")

        old_md = sa.MetaData()
        old = sa.Table("novels", old_md, autoload_with=bind)

        tmp_md = sa.MetaData()
        tmp = old.to_metadata(tmp_md, name=tmp_table_name)
        tmp.dialect_options["sqlite"]["autoincrement"] = autoincrement

        create_sql = str(sa.schema.CreateTable(tmp).compile(dialect=bind.dialect))
        bind.exec_driver_sql(create_sql)

        col_names = [c.name for c in old.columns]
        select_stmt = sa.select(*(old.c[name] for name in col_names))
        bind.execute(tmp.insert().from_select(col_names, select_stmt))

        bind.exec_driver_sql("DROP TABLE novels")
        bind.exec_driver_sql(f"ALTER TABLE {tmp_table_name} RENAME TO novels")

        # Keep sqlite_sequence in sync so the next insert picks MAX(id)+1.
        # NOTE: sqlite_sequence exists only after creating an AUTOINCREMENT table.
        if autoincrement:
            bind.execute(sa.text("DELETE FROM sqlite_sequence WHERE name='novels'"))
            bind.execute(
                sa.text(
                    "INSERT INTO sqlite_sequence(name, seq) "
                    "VALUES ('novels', (SELECT COALESCE(MAX(id), 0) FROM novels))"
                )
            )
        else:
            # Best-effort cleanup; ignore if sqlite_sequence doesn't exist.
            try:
                bind.execute(sa.text("DELETE FROM sqlite_sequence WHERE name='novels'"))
            except sa.exc.DBAPIError:
                pass

        # Restore SQL-backed indexes and triggers that existed on the original
        # table (e.g., created by create_all() or manual setup).
        for sql in index_sql:
            bind.exec_driver_sql(sql)

        # Restore any triggers that existed on the original table.
        for sql in trigger_sql:
            bind.exec_driver_sql(sql)


def upgrade() -> None:
    bind = op.get_bind()
    if bind is None or not _is_sqlite(bind):
        return

    if _has_autoincrement(bind):
        return

    _rebuild_novels_table(autoincrement=True)


def downgrade() -> None:
    bind = op.get_bind()
    if bind is None or not _is_sqlite(bind):
        return

    if not _has_autoincrement(bind):
        return

    _rebuild_novels_table(autoincrement=False)
