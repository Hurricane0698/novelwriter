from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from app.database import Base
from app.selfhost_db_bootstrap import (
    _MISSING_TABLE,
    _matching_unversioned_upgrade_baseline,
    _missing_required_columns,
    ensure_selfhost_database_ready,
)


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


def _degrade_schema_from_036_to_035(conn) -> None:
    conn.execute(sa.text("DROP TABLE world_generation_runs"))
    conn.execute(sa.text("ALTER TABLE continuation_runs RENAME TO continuation_runs_old"))
    conn.execute(
        sa.text(
            """
            CREATE TABLE continuation_runs (
                id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                novel_id INTEGER NOT NULL,
                client_request_id VARCHAR(64) NOT NULL,
                request_hash VARCHAR(64) NOT NULL,
                claim_token VARCHAR(64) NOT NULL,
                status VARCHAR(20) NOT NULL,
                delivered_count INTEGER NOT NULL,
                continuation_ids JSON,
                debug_summary JSON,
                error_code VARCHAR(64),
                error_message TEXT,
                completed_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                CONSTRAINT uq_continuation_runs_user_novel_request UNIQUE (user_id, novel_id, client_request_id),
                FOREIGN KEY(user_id) REFERENCES users (id),
                FOREIGN KEY(novel_id) REFERENCES novels (id)
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO continuation_runs (
                id,
                user_id,
                novel_id,
                client_request_id,
                request_hash,
                claim_token,
                status,
                delivered_count,
                continuation_ids,
                debug_summary,
                error_code,
                error_message,
                completed_at,
                created_at,
                updated_at
            )
            SELECT
                id,
                user_id,
                novel_id,
                client_request_id,
                request_hash,
                claim_token,
                status,
                delivered_count,
                continuation_ids,
                debug_summary,
                error_code,
                error_message,
                completed_at,
                created_at,
                updated_at
            FROM continuation_runs_old
            """
        )
    )
    conn.execute(sa.text("DROP TABLE continuation_runs_old"))
    conn.execute(sa.text("CREATE INDEX ix_continuation_runs_novel_status ON continuation_runs (novel_id, status)"))


def _alembic_config(db_url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", db_url)
    return config


def _stamp_database(
    monkeypatch: pytest.MonkeyPatch, db_url: str, revision: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.stamp(_alembic_config(db_url), revision)


def _recorded_revision(engine) -> str:
    with engine.connect() as conn:
        return str(
            conn.execute(
                sa.text("SELECT version_num FROM alembic_version")
            ).scalar_one()
        )


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
    assert "content_format" in {
        column["name"] for column in inspector.get_columns("novels")
    }
    assert "source_volume_title" in {
        column["name"] for column in inspector.get_columns("chapters")
    }
    assert "error_code" in {
        column["name"] for column in inspector.get_columns("novel_ingest_jobs")
    }
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one() == "wal"
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


def test_fresh_schema_preserves_auth_and_quota_user_not_null_invariants(sqlite_engine):
    engine, _db_url = sqlite_engine
    Base.metadata.create_all(bind=engine)

    inspector = sa.inspect(engine)
    auth_columns = {column["name"]: column for column in inspector.get_columns("auth_identities")}
    quota_columns = {column["name"]: column for column in inspector.get_columns("quota_reservations")}
    user_event_columns = {column["name"]: column for column in inspector.get_columns("user_events")}

    assert auth_columns["user_id"]["nullable"] is False
    assert quota_columns["user_id"]["nullable"] is False
    assert user_event_columns["user_id"]["nullable"] is True


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


def test_auto_upgrades_unversioned_schema_missing_only_continuation_semantic_admission(sqlite_engine):
    engine, db_url = sqlite_engine
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        _degrade_schema_from_036_to_035(conn)

    calls: list[tuple[str, str]] = []

    result = ensure_selfhost_database_ready(
        db_engine=engine,
        metadata=Base.metadata,
        db_url=db_url,
        stamp_fn=lambda _config, revision: calls.append(("stamp", revision)),
        upgrade_fn=lambda _config, revision: calls.append(("upgrade", revision)),
    )

    assert result == "upgraded"
    assert calls == [("stamp", "035"), ("upgrade", "head")]


def test_repairs_partial_versioned_upgrade_when_schema_is_already_at_later_baseline(sqlite_engine):
    engine, db_url = sqlite_engine
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        _degrade_schema_from_036_to_035(conn)
        conn.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        conn.execute(sa.text("INSERT INTO alembic_version (version_num) VALUES ('031')"))

    calls: list[tuple[str, str]] = []

    result = ensure_selfhost_database_ready(
        db_engine=engine,
        metadata=Base.metadata,
        db_url=db_url,
        stamp_fn=lambda _config, revision: calls.append(("stamp", revision)),
        upgrade_fn=lambda _config, revision: calls.append(("upgrade", revision)),
    )

    assert result == "upgraded"
    assert calls == [("stamp", "035"), ("upgrade", "head")]


def test_matches_unversioned_baseline_for_chapter_source_metadata():
    missing_columns = {
        "auth_identities": {
            _MISSING_TABLE,
            "user_id",
            "provider",
            "provider_user_id",
            "provider_login",
            "provider_email",
            "last_login_at",
        },
        "chapters": {"source_chapter_label", "source_chapter_number"},
    }

    assert _matching_unversioned_upgrade_baseline(missing_columns) == "030"


def test_matches_unversioned_baseline_for_markdown_source_contract():
    missing_columns = {
        "novels": {"content_format"},
        "chapters": {"source_volume_title"},
        "novel_ingest_jobs": {"error_code"},
        "novel_context_summaries": {
            _MISSING_TABLE,
            "novel_id",
            "start_chapter",
            "end_chapter",
            "title",
            "content",
            "model",
            "source_fingerprint",
            "review_status",
            "created_at",
            "updated_at",
        },
    }

    assert _matching_unversioned_upgrade_baseline(missing_columns) == "040"


def test_matches_latest_safe_baseline_when_schema_is_current():
    assert _matching_unversioned_upgrade_baseline({}) == "041"


def test_matches_unversioned_baseline_missing_only_context_summaries():
    assert _matching_unversioned_upgrade_baseline(
        {"novel_context_summaries": {_MISSING_TABLE}},
    ) == "041"


def test_revision_032_upgrade_creates_generation_admission_tables_and_preserves_data(
    sqlite_engine,
    monkeypatch: pytest.MonkeyPatch,
):
    engine, db_url = sqlite_engine
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(sa.text("DROP TABLE world_generation_runs"))
        conn.execute(sa.text("DROP TABLE novel_ingest_jobs"))
        conn.execute(sa.text("DROP TABLE continuation_runs"))
        conn.execute(
            sa.text(
                """
                INSERT INTO users (
                    username,
                    hashed_password,
                    role,
                    is_active,
                    nickname,
                    generation_quota,
                    feedback_submitted
                ) VALUES (
                    'issue-9-user',
                    'hash',
                    'user',
                    1,
                    'Issue 9',
                    5,
                    0
                )
                """
            )
        )
        gaps = _missing_required_columns(conn)
    _stamp_database(monkeypatch, db_url, "032")

    assert _MISSING_TABLE in gaps["continuation_runs"]
    assert _matching_unversioned_upgrade_baseline(gaps) == "032"

    result = ensure_selfhost_database_ready(
        db_engine=engine,
        metadata=Base.metadata,
        db_url=db_url,
    )

    inspector = sa.inspect(engine)
    assert result == "upgraded"
    assert _recorded_revision(engine) == "042"
    assert {"continuation_runs", "world_generation_runs"}.issubset(
        inspector.get_table_names()
    )
    assert "uq_continuation_runs_active_semantic" in {
        index["name"] for index in inspector.get_indexes("continuation_runs")
    }
    with engine.connect() as conn:
        nickname = conn.execute(
            sa.text("SELECT nickname FROM users WHERE username = 'issue-9-user'")
        ).scalar_one()
    assert nickname == "Issue 9"


def test_repairs_v032_database_already_stamped_past_continuation_table_creation(
    sqlite_engine,
    monkeypatch: pytest.MonkeyPatch,
):
    engine, db_url = sqlite_engine
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(sa.text("DROP TABLE continuation_runs"))
    _stamp_database(monkeypatch, db_url, "037")

    result = ensure_selfhost_database_ready(
        db_engine=engine,
        metadata=Base.metadata,
        db_url=db_url,
    )

    inspector = sa.inspect(engine)
    continuation_columns = {
        column["name"] for column in inspector.get_columns("continuation_runs")
    }
    world_generation_columns = {
        column["name"] for column in inspector.get_columns("world_generation_runs")
    }
    assert result == "upgraded"
    assert _recorded_revision(engine) == "042"
    assert {
        "client_request_id",
        "request_hash",
        "semantic_key",
        "claim_token",
    }.issubset(continuation_columns)
    assert "request_hash" not in world_generation_columns
    assert "response_payload" not in world_generation_columns


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
        stamp_fn=lambda _config, revision: calls.append(("stamp", revision)),
        upgrade_fn=lambda _config, revision: calls.append(("upgrade", revision)),
    )

    assert result == "upgraded"
    assert calls == [("stamp", "041"), ("upgrade", "head")]
