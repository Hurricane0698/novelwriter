"""
Regression: migration 016 must not silently drop SQLite schema objects on `novels`.

`alembic/versions/016_sqlite_novels_autoincrement.py` rebuilds the `novels` table
to add/remove SQLite `AUTOINCREMENT`. A table rebuild can accidentally drop
indexes/constraints/triggers if it uses hard-coded DDL.

This test creates an extra index + trigger on `novels` before upgrading to 016
and asserts they're preserved, and that AUTOINCREMENT is present afterwards.
"""

from __future__ import annotations

from pathlib import Path
import importlib.util
import sqlite3

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_migration_016():
    path = _repo_root() / "alembic" / "versions" / "016_sqlite_novels_autoincrement.py"
    spec = importlib.util.spec_from_file_location("migration_016", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _sqlite_scalar(db_path: Path, sql: str) -> str:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(sql).fetchone()
        assert row is not None
        return str(row[0])


def _sqlite_exists(db_path: Path, *, type_: str, name: str) -> bool:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type=? AND name=?",
            (type_, name),
        ).fetchone()
        return row is not None


def test_migration_016_preserves_indexes_and_triggers(tmp_path: Path):
    db_path = tmp_path / "alembic_016.db"
    engine = sa.create_engine(f"sqlite:///{db_path}")

    # Create a "pre-016" novels table (no AUTOINCREMENT) plus extra objects that
    # must survive the rebuild.
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE novels (
                id INTEGER NOT NULL PRIMARY KEY,
                title TEXT NOT NULL
            )
            """
        )
        conn.exec_driver_sql("CREATE INDEX ix_novels_title ON novels(title)")
        conn.exec_driver_sql(
            "CREATE TRIGGER trg_novels_noop AFTER INSERT ON novels "
            "BEGIN SELECT 1; END;"
        )

    migration_016 = _load_migration_016()

    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        ops = Operations(ctx)

        # Patch the migration module's `op` to run in our test context.
        migration_016.op = ops
        migration_016.upgrade()

    novels_sql = _sqlite_scalar(
        db_path,
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='novels'",
    ).upper()
    assert "AUTOINCREMENT" in novels_sql
    assert _sqlite_exists(db_path, type_="index", name="ix_novels_title")
    assert _sqlite_exists(db_path, type_="trigger", name="trg_novels_noop")
