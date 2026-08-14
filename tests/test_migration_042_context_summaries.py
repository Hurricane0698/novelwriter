from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError


def _load_migration():
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "042_add_context_summaries.py"
    )
    spec = importlib.util.spec_from_file_location("migration_042", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(module, engine: sa.Engine, step: str) -> None:
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        module.op = Operations(context)
        getattr(module, step)()


def test_migration_042_creates_reviewed_context_summaries_and_downgrades(tmp_path: Path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE novels (id INTEGER PRIMARY KEY, title TEXT NOT NULL)"
        )
        connection.exec_driver_sql("INSERT INTO novels (id, title) VALUES (1, 'Novel')")

    migration = _load_migration()
    _run(migration, engine, "upgrade")

    inspector = sa.inspect(engine)
    assert "novel_context_summaries" in inspector.get_table_names()
    assert {column["name"] for column in inspector.get_columns("novel_context_summaries")} >= {
        "novel_id",
        "start_chapter",
        "end_chapter",
        "content",
        "model",
        "source_fingerprint",
        "review_status",
    }
    assert {
        constraint["name"]
        for constraint in inspector.get_check_constraints("novel_context_summaries")
    } == {
        "ck_novel_context_summaries_range_order",
        "ck_novel_context_summaries_review_status",
        "ck_novel_context_summaries_start_positive",
    }

    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO novel_context_summaries (
                    novel_id, start_chapter, end_chapter, title, content,
                    source_fingerprint, review_status
                ) VALUES (1, 1, 2, 'Recap', 'Summary', :fingerprint, 'confirmed')
                """
            ),
            {"fingerprint": "0" * 64},
        )

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO novel_context_summaries (
                    novel_id, start_chapter, end_chapter, title, content,
                    source_fingerprint, review_status
                ) VALUES (1, 3, 2, 'Invalid', 'Summary', :fingerprint, 'confirmed')
                """
            ),
            {"fingerprint": "0" * 64},
        )

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO novel_context_summaries (
                    novel_id, start_chapter, end_chapter, title, content,
                    source_fingerprint, review_status
                ) VALUES (1, 1, 1, 'Invalid', 'Summary', :fingerprint, 'published')
                """
            ),
            {"fingerprint": "0" * 64},
        )

    _run(migration, engine, "downgrade")
    assert "novel_context_summaries" not in sa.inspect(engine).get_table_names()


def test_migration_042_upgrade_is_idempotent_for_current_table(tmp_path: Path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'current.db'}")
    migration = _load_migration()
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE novels (id INTEGER PRIMARY KEY, title TEXT NOT NULL)"
        )

    _run(migration, engine, "upgrade")
    _run(migration, engine, "upgrade")

    indexes = {
        index["name"]
        for index in sa.inspect(engine).get_indexes("novel_context_summaries")
    }
    assert indexes == {"ix_novel_context_summaries_novel_range"}
