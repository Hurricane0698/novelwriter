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
        / "041_add_markdown_native_source_contract.py"
    )
    spec = importlib.util.spec_from_file_location("migration_041", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(module, engine: sa.Engine, step: str) -> None:
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        module.op = Operations(context)
        getattr(module, step)()


def test_migration_041_backfills_plain_text_and_enforces_new_contract(tmp_path: Path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE novels (id INTEGER PRIMARY KEY, title TEXT NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE chapters (id INTEGER PRIMARY KEY, novel_id INTEGER NOT NULL, content TEXT NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE novel_ingest_jobs (id INTEGER PRIMARY KEY, novel_id INTEGER NOT NULL, status TEXT NOT NULL)"
        )
        connection.exec_driver_sql("INSERT INTO novels (id, title) VALUES (1, 'Legacy')")
        connection.exec_driver_sql(
            "INSERT INTO chapters (id, novel_id, content) VALUES (1, 1, '正文')"
        )
        connection.exec_driver_sql(
            "INSERT INTO novel_ingest_jobs (id, novel_id, status) VALUES (1, 1, 'failed')"
        )

    migration = _load_migration()
    _run(migration, engine, "upgrade")

    inspector = sa.inspect(engine)
    assert "content_format" in {column["name"] for column in inspector.get_columns("novels")}
    assert "source_volume_title" in {
        column["name"] for column in inspector.get_columns("chapters")
    }
    assert "error_code" in {
        column["name"] for column in inspector.get_columns("novel_ingest_jobs")
    }
    with engine.connect() as connection:
        assert connection.execute(
            sa.text("SELECT content_format FROM novels WHERE id = 1")
        ).scalar_one() == "plain_text"
        assert connection.execute(
            sa.text("SELECT error_code FROM novel_ingest_jobs WHERE id = 1")
        ).scalar_one() == "ingest_internal_error"

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text("UPDATE novels SET content_format = 'unknown' WHERE id = 1")
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text("UPDATE novel_ingest_jobs SET error_code = 'unknown' WHERE id = 1")
        )

    with engine.begin() as connection:
        connection.execute(
            sa.text("UPDATE novels SET content_format = 'markdown' WHERE id = 1")
        )
        connection.execute(
            sa.text("UPDATE chapters SET source_volume_title = '第一卷' WHERE id = 1")
        )

    _run(migration, engine, "downgrade")

    inspector = sa.inspect(engine)
    assert "content_format" not in {column["name"] for column in inspector.get_columns("novels")}
    assert "source_volume_title" not in {
        column["name"] for column in inspector.get_columns("chapters")
    }
    assert "error_code" not in {
        column["name"] for column in inspector.get_columns("novel_ingest_jobs")
    }
    with engine.connect() as connection:
        assert connection.execute(
            sa.text("SELECT content FROM chapters WHERE id = 1")
        ).scalar_one() == "正文"


def test_migration_041_accepts_current_metadata_schema_without_overwriting_values(
    tmp_path: Path,
):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'current-metadata.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE novels (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                content_format VARCHAR(20) NOT NULL,
                CONSTRAINT ck_novels_content_format
                    CHECK (content_format IN ('plain_text', 'markdown'))
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE chapters (
                id INTEGER PRIMARY KEY,
                novel_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                source_volume_title VARCHAR(255)
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE novel_ingest_jobs (
                id INTEGER PRIMARY KEY,
                novel_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                error_code VARCHAR(64),
                CONSTRAINT ck_novel_ingest_jobs_error_code
                    CHECK (
                        error_code IS NULL OR error_code IN (
                            'source_missing',
                            'source_encoding_unsupported',
                            'markdown_structure_invalid',
                            'ingest_internal_error'
                        )
                    )
            )
            """
        )
        connection.exec_driver_sql(
            "INSERT INTO novels (id, title, content_format) "
            "VALUES (1, 'Native', 'markdown')"
        )
        connection.exec_driver_sql(
            "INSERT INTO chapters (id, novel_id, content, source_volume_title) "
            "VALUES (1, 1, '正文', '第一卷')"
        )
        connection.exec_driver_sql(
            "INSERT INTO novel_ingest_jobs (id, novel_id, status, error_code) "
            "VALUES (1, 1, 'failed', 'markdown_structure_invalid')"
        )

    migration = _load_migration()
    _run(migration, engine, "upgrade")

    inspector = sa.inspect(engine)
    assert {constraint["name"] for constraint in inspector.get_check_constraints("novels")} == {
        "ck_novels_content_format"
    }
    assert {
        constraint["name"]
        for constraint in inspector.get_check_constraints("novel_ingest_jobs")
    } == {"ck_novel_ingest_jobs_error_code"}
    with engine.connect() as connection:
        row = connection.execute(
            sa.text(
                """
                SELECT
                    novels.content_format,
                    chapters.source_volume_title,
                    novel_ingest_jobs.error_code
                FROM novels
                JOIN chapters ON chapters.novel_id = novels.id
                JOIN novel_ingest_jobs ON novel_ingest_jobs.novel_id = novels.id
                WHERE novels.id = 1
                """
            )
        ).one()
    assert row == ("markdown", "第一卷", "markdown_structure_invalid")
