from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine
from sqlalchemy.schema import MetaData

from app.database import Base, DATABASE_URL, engine
from app.models import (  # noqa: F401 - register models with Base.metadata
    BootstrapJob,
    Chapter,
    Continuation,
    Exploration,
    ExplorationChapter,
    LoreEntry,
    LoreKey,
    Novel,
    Outline,
    TokenUsage,
    User,
    UserEvent,
    WorldEntity,
    WorldEntityAttribute,
    WorldRelationship,
    WorldSystem,
)

logger = logging.getLogger(__name__)

_HEAD_REVISION = "head"
_CORE_TABLES = {"novels", "chapters"}
_LEGACY_TABLES = {
    "narrative_events",
    "narrative_facts",
    "narrative_styles",
    "character_arcs",
    "character_epochs",
    "character_moments",
    "plot_arcs",
    "plot_threads",
    "plot_beats",
}
_REQUIRED_SCHEMA_COLUMNS: dict[str, set[str]] = {
    "novels": {"owner_id", "window_index"},
    "world_entities": {"origin", "worldpack_pack_id", "worldpack_key"},
    "world_entity_attributes": {"surface", "origin", "worldpack_pack_id"},
    "world_relationships": {"origin", "worldpack_pack_id", "label_canonical"},
    "world_systems": {"origin", "worldpack_pack_id"},
    "users": {"nickname", "generation_quota", "feedback_submitted", "feedback_answers", "preferences"},
    "bootstrap_jobs": {"mode", "draft_policy", "initialized"},
    "user_events": {"user_id", "event", "created_at"},
}


def _alembic_config(*, db_url: str, ini_path: str | Path = "alembic.ini") -> Config:
    config = Config(str(ini_path))
    config.set_main_option("sqlalchemy.url", db_url)
    return config


def _user_tables(bind) -> set[str]:
    inspector = sa.inspect(bind)
    return {
        table_name
        for table_name in inspector.get_table_names()
        if not table_name.startswith("sqlite_")
    }


def _missing_required_columns(bind) -> dict[str, set[str]]:
    inspector = sa.inspect(bind)
    missing: dict[str, set[str]] = {}
    for table_name, required_columns in _REQUIRED_SCHEMA_COLUMNS.items():
        try:
            existing = {column["name"] for column in inspector.get_columns(table_name)}
        except Exception:
            missing[table_name] = set(required_columns)
            continue
        absent = required_columns - existing
        if absent:
            missing[table_name] = absent
    return missing


def _reset_incomplete_bootstrap(bind) -> None:
    reset_tables = (
        _user_tables(bind)
        & ({*Base.metadata.tables.keys(), *_LEGACY_TABLES, "alembic_version"})
    )
    if not reset_tables:
        return

    reflected = MetaData()
    reflected.reflect(bind=bind, only=sorted(reset_tables))
    reflected.drop_all(bind=bind)


def ensure_selfhost_database_ready(
    *,
    db_engine: Engine,
    metadata: MetaData,
    db_url: str,
    ini_path: str | Path = "alembic.ini",
    stamp_fn: Callable[[Config, str], None] | None = None,
    upgrade_fn: Callable[[Config, str], None] | None = None,
) -> str:
    stamp = stamp_fn or command.stamp
    upgrade = upgrade_fn or command.upgrade

    with db_engine.begin() as bind:
        tables = _user_tables(bind)

        if not _CORE_TABLES.issubset(tables):
            logger.warning(
                "Database missing core selfhost tables; rebuilding current schema and stamping Alembic head."
            )
            _reset_incomplete_bootstrap(bind)
            metadata.create_all(bind=bind)
            stamp(_alembic_config(db_url=db_url, ini_path=ini_path), _HEAD_REVISION)
            return "bootstrapped"

        if "alembic_version" not in tables:
            missing_columns = _missing_required_columns(bind)
            if missing_columns:
                raise RuntimeError(
                    "Database has application tables but no alembic_version table, and it does not match "
                    "the current schema closely enough to auto-stamp safely. Missing columns: "
                    f"{missing_columns}. Back up the database, then rebuild or migrate it manually."
                )

            logger.warning(
                "Database has current application tables but no alembic_version; stamping Alembic head."
            )
            stamp(_alembic_config(db_url=db_url, ini_path=ini_path), _HEAD_REVISION)
            return "stamped"

    upgrade(_alembic_config(db_url=db_url, ini_path=ini_path), _HEAD_REVISION)
    return "upgraded"


def main() -> None:
    ensure_selfhost_database_ready(
        db_engine=engine,
        metadata=Base.metadata,
        db_url=DATABASE_URL,
    )


if __name__ == "__main__":
    main()
