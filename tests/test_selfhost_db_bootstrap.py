from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from app.database import Base
from app.selfhost_db_bootstrap import ensure_selfhost_database_ready


@pytest.fixture()
def sqlite_engine(tmp_path: Path):
    db_path = tmp_path / "bootstrap.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    try:
        yield engine, f"sqlite:///{db_path}"
    finally:
        engine.dispose()


def test_bootstraps_fresh_database_and_stamps_head(sqlite_engine):
    engine, db_url = sqlite_engine
    calls: list[tuple[str, str]] = []

    def fake_stamp(_config, revision):
        calls.append(("stamp", revision))

    result = ensure_selfhost_database_ready(
        db_engine=engine,
        metadata=Base.metadata,
        db_url=db_url,
        stamp_fn=fake_stamp,
        upgrade_fn=lambda *_args: pytest.fail("upgrade should not run for a fresh database"),
    )

    inspector = sa.inspect(engine)
    assert result == "bootstrapped"
    assert "novels" in inspector.get_table_names()
    assert "world_entity_attributes" in inspector.get_table_names()
    assert calls == [("stamp", "head")]


def test_resets_partial_bootstrap_before_creating_current_schema(sqlite_engine):
    engine, db_url = sqlite_engine
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(255) NOT NULL)"))
        conn.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        conn.execute(sa.text("INSERT INTO alembic_version (version_num) VALUES ('009')"))

    ensure_selfhost_database_ready(
        db_engine=engine,
        metadata=Base.metadata,
        db_url=db_url,
        stamp_fn=lambda *_args: None,
        upgrade_fn=lambda *_args: pytest.fail("upgrade should not run for an incomplete bootstrap"),
    )

    inspector = sa.inspect(engine)
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    assert {"nickname", "feedback_answers", "preferences"}.issubset(user_columns)
    assert "novels" in inspector.get_table_names()


def test_stamps_current_unversioned_schema(sqlite_engine):
    engine, db_url = sqlite_engine
    Base.metadata.create_all(bind=engine)
    calls: list[tuple[str, str]] = []

    result = ensure_selfhost_database_ready(
        db_engine=engine,
        metadata=Base.metadata,
        db_url=db_url,
        stamp_fn=lambda _config, revision: calls.append(("stamp", revision)),
        upgrade_fn=lambda *_args: pytest.fail("upgrade should not run when schema is already current"),
    )

    assert result == "stamped"
    assert calls == [("stamp", "head")]


def test_auto_upgrades_unversioned_schema_missing_only_novel_language(sqlite_engine):
    engine, db_url = sqlite_engine
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE novels (id INTEGER PRIMARY KEY, owner_id INTEGER, window_index JSON)"))
        conn.execute(sa.text("CREATE TABLE chapters (id INTEGER PRIMARY KEY, novel_id INTEGER NOT NULL, chapter_number INTEGER NOT NULL)"))
        conn.execute(
            sa.text(
                "CREATE TABLE world_entities (id INTEGER PRIMARY KEY, origin VARCHAR(50), worldpack_pack_id INTEGER, worldpack_key VARCHAR(255))"
            )
        )
        conn.execute(
            sa.text(
                "CREATE TABLE world_entity_attributes (id INTEGER PRIMARY KEY, surface TEXT, origin VARCHAR(50), worldpack_pack_id INTEGER)"
            )
        )
        conn.execute(
            sa.text(
                "CREATE TABLE world_relationships (id INTEGER PRIMARY KEY, origin VARCHAR(50), worldpack_pack_id INTEGER, label_canonical VARCHAR(255))"
            )
        )
        conn.execute(
            sa.text(
                "CREATE TABLE world_systems (id INTEGER PRIMARY KEY, origin VARCHAR(50), worldpack_pack_id INTEGER)"
            )
        )
        conn.execute(
            sa.text(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, nickname VARCHAR(255), generation_quota INTEGER, feedback_submitted BOOLEAN, feedback_answers JSON, preferences JSON)"
            )
        )
        conn.execute(
            sa.text(
                "CREATE TABLE bootstrap_jobs (id INTEGER PRIMARY KEY, mode VARCHAR(50), draft_policy VARCHAR(50), initialized BOOLEAN)"
            )
        )
        conn.execute(
            sa.text(
                "CREATE TABLE user_events (id INTEGER PRIMARY KEY, user_id INTEGER, event VARCHAR(255), created_at DATETIME)"
            )
        )

    calls: list[tuple[str, str]] = []

    result = ensure_selfhost_database_ready(
        db_engine=engine,
        metadata=Base.metadata,
        db_url=db_url,
        stamp_fn=lambda _config, revision: calls.append(("stamp", revision)),
        upgrade_fn=lambda _config, revision: calls.append(("upgrade", revision)),
    )

    assert result == "upgraded"
    assert calls == [("stamp", "022"), ("upgrade", "head")]


def test_auto_upgrades_unversioned_schema_missing_only_derived_asset_jobs(sqlite_engine):
    engine, db_url = sqlite_engine
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(sa.text("DROP TABLE derived_asset_jobs"))

    calls: list[tuple[str, str]] = []

    result = ensure_selfhost_database_ready(
        db_engine=engine,
        metadata=Base.metadata,
        db_url=db_url,
        stamp_fn=lambda _config, revision: calls.append(("stamp", revision)),
        upgrade_fn=lambda _config, revision: calls.append(("upgrade", revision)),
    )

    assert result == "upgraded"
    assert calls == [("stamp", "029"), ("upgrade", "head")]


def test_rejects_stale_unversioned_schema(sqlite_engine):
    engine, db_url = sqlite_engine
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE novels (id INTEGER PRIMARY KEY, title VARCHAR(255) NOT NULL)"))
        conn.execute(sa.text("CREATE TABLE chapters (id INTEGER PRIMARY KEY, novel_id INTEGER NOT NULL, chapter_number INTEGER NOT NULL)"))

    with pytest.raises(RuntimeError, match="no alembic_version"):
        ensure_selfhost_database_ready(
            db_engine=engine,
            metadata=Base.metadata,
            db_url=db_url,
            stamp_fn=lambda *_args: None,
            upgrade_fn=lambda *_args: None,
        )


def test_upgrades_versioned_schema(sqlite_engine):
    engine, db_url = sqlite_engine
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        conn.execute(sa.text("INSERT INTO alembic_version (version_num) VALUES ('020')"))

    calls: list[tuple[str, str]] = []

    result = ensure_selfhost_database_ready(
        db_engine=engine,
        metadata=Base.metadata,
        db_url=db_url,
        stamp_fn=lambda *_args: pytest.fail("stamp should not run for a versioned database"),
        upgrade_fn=lambda _config, revision: calls.append(("upgrade", revision)),
    )

    assert result == "upgraded"
    assert calls == [("upgrade", "head")]
