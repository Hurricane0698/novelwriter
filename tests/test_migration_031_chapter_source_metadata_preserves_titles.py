"""
Regression: migration 031 must not rewrite ambiguous historic chapter titles.

`alembic/versions/031_add_chapter_source_metadata.py` introduces source-label
columns for future imports. Historical `chapters.title` values are already
user-editable, so the migration must not try to infer provenance and rewrite
them during upgrade or downgrade.
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


def _load_migration_031():
    path = _repo_root() / "alembic" / "versions" / "031_add_chapter_source_metadata.py"
    spec = importlib.util.spec_from_file_location("migration_031", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _run_migration_step(module, engine: sa.Engine, *, step: str) -> None:
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        ops = Operations(ctx)
        module.op = ops
        getattr(module, step)()


def _sqlite_columns(db_path: Path, table: str) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [str(row[1]) for row in rows]


def test_migration_031_upgrade_keeps_historic_titles_untouched(tmp_path: Path):
    db_path = tmp_path / "alembic_031_upgrade.db"
    engine = sa.create_engine(f"sqlite:///{db_path}")

    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE chapters (
                id INTEGER NOT NULL PRIMARY KEY,
                title TEXT NOT NULL
            )
            """
        )
        conn.exec_driver_sql(
            """
            INSERT INTO chapters (id, title) VALUES
                (1, '序章'),
                (2, 'Prologue'),
                (3, '番外篇'),
                (4, 'Chapter 7'),
                (5, '第844章 归来')
            """
        )

    migration_031 = _load_migration_031()
    _run_migration_step(migration_031, engine, step="upgrade")

    assert _sqlite_columns(db_path, "chapters") == ["id", "title", "source_chapter_label", "source_chapter_number"]

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, title, source_chapter_label, source_chapter_number
            FROM chapters
            ORDER BY id
            """
        ).fetchall()

    assert rows == [
        (1, "序章", None, None),
        (2, "Prologue", None, None),
        (3, "番外篇", None, None),
        (4, "Chapter 7", None, None),
        (5, "第844章 归来", None, None),
    ]


def test_migration_031_downgrade_keeps_post_upgrade_title_edits(tmp_path: Path):
    db_path = tmp_path / "alembic_031_downgrade.db"
    engine = sa.create_engine(f"sqlite:///{db_path}")

    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE chapters (
                id INTEGER NOT NULL PRIMARY KEY,
                title TEXT NOT NULL
            )
            """
        )
        conn.exec_driver_sql("INSERT INTO chapters (id, title) VALUES (1, '原始标题')")

    migration_031 = _load_migration_031()
    _run_migration_step(migration_031, engine, step="upgrade")

    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            UPDATE chapters
            SET title = '用户改后的标题',
                source_chapter_label = '第844章 归来',
                source_chapter_number = 844
            WHERE id = 1
            """
        )

    _run_migration_step(migration_031, engine, step="downgrade")

    assert _sqlite_columns(db_path, "chapters") == ["id", "title"]

    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT title FROM chapters WHERE id = 1").fetchone()

    assert row == ("用户改后的标题",)
