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
    ContinuationRun,
    DerivedAssetJob,
    Exploration,
    ExplorationChapter,
    Novel,
    NovelIngestJob,
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
_PRE_NOVEL_LANGUAGE_REVISION = "022"
_PRE_DERIVED_ASSET_JOB_REVISION = "029"
_PRE_CHAPTER_SOURCE_METADATA_REVISION = "030"
_PRE_AUTH_IDENTITIES_REVISION = "032"
_PRE_NOVEL_INGEST_JOB_REVISION = "034"
_PRE_WORLD_GENERATION_ADMISSION_REVISION = "035"
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
    "chapters": {"source_chapter_label", "source_chapter_number"},
    "auth_identities": {
        "user_id",
        "provider",
        "provider_user_id",
        "provider_login",
        "provider_email",
        "last_login_at",
    },
    "novels": {
        "owner_id",
        "window_index",
        "language",
        "window_index_status",
        "window_index_revision",
        "window_index_built_revision",
        "window_index_error",
    },
    "world_entities": {"origin", "worldpack_pack_id", "worldpack_key"},
    "world_entity_attributes": {"surface", "origin", "worldpack_pack_id"},
    "world_relationships": {"origin", "worldpack_pack_id", "label_canonical"},
    "world_systems": {"origin", "worldpack_pack_id"},
    "users": {"nickname", "generation_quota", "feedback_submitted", "feedback_answers", "preferences"},
    "bootstrap_jobs": {"mode", "draft_policy", "initialized"},
    "continuation_runs": {"semantic_key"},
    "derived_asset_jobs": {
        "asset_kind",
        "status",
        "target_revision",
        "claimed_revision",
        "completed_revision",
        "result",
        "error",
        "lease_owner",
        "lease_expires_at",
        "started_at",
        "finished_at",
    },
    "novel_ingest_jobs": {
        "status",
        "stage",
        "size_tier",
        "source_bytes",
        "source_chars",
        "chapter_count",
        "requested_language",
        "resolved_language",
        "auto_index_plan",
        "bootstrap_plan",
        "readiness_mode",
        "error",
        "lease_owner",
        "lease_expires_at",
        "started_at",
        "finished_at",
    },
    "user_events": {"user_id", "event", "created_at"},
    "world_generation_runs": {
        "request_hash",
        "claim_token",
        "status",
        "response_payload",
        "error_code",
        "error_message",
        "completed_at",
    },
}
_UNVERSIONED_AUTO_UPGRADE_BASELINES: tuple[tuple[str, dict[str, set[str]]], ...] = (
    (
        _PRE_WORLD_GENERATION_ADMISSION_REVISION,
        {
            "continuation_runs": _REQUIRED_SCHEMA_COLUMNS["continuation_runs"],
            "world_generation_runs": _REQUIRED_SCHEMA_COLUMNS["world_generation_runs"],
        },
    ),
    (
        _PRE_NOVEL_INGEST_JOB_REVISION,
        {
            "continuation_runs": _REQUIRED_SCHEMA_COLUMNS["continuation_runs"],
            "novel_ingest_jobs": _REQUIRED_SCHEMA_COLUMNS["novel_ingest_jobs"],
            "world_generation_runs": _REQUIRED_SCHEMA_COLUMNS["world_generation_runs"],
        },
    ),
    (
        _PRE_AUTH_IDENTITIES_REVISION,
        {
            "continuation_runs": _REQUIRED_SCHEMA_COLUMNS["continuation_runs"],
            "novel_ingest_jobs": _REQUIRED_SCHEMA_COLUMNS["novel_ingest_jobs"],
            "world_generation_runs": _REQUIRED_SCHEMA_COLUMNS["world_generation_runs"],
        },
    ),
    (
        _PRE_CHAPTER_SOURCE_METADATA_REVISION,
        {
            "auth_identities": _REQUIRED_SCHEMA_COLUMNS["auth_identities"],
            "chapters": _REQUIRED_SCHEMA_COLUMNS["chapters"],
            "continuation_runs": _REQUIRED_SCHEMA_COLUMNS["continuation_runs"],
            "world_generation_runs": _REQUIRED_SCHEMA_COLUMNS["world_generation_runs"],
        },
    ),
    (
        _PRE_DERIVED_ASSET_JOB_REVISION,
        {
            "auth_identities": _REQUIRED_SCHEMA_COLUMNS["auth_identities"],
            "chapters": _REQUIRED_SCHEMA_COLUMNS["chapters"],
            "continuation_runs": _REQUIRED_SCHEMA_COLUMNS["continuation_runs"],
            "derived_asset_jobs": _REQUIRED_SCHEMA_COLUMNS["derived_asset_jobs"],
            "novel_ingest_jobs": _REQUIRED_SCHEMA_COLUMNS["novel_ingest_jobs"],
            "world_generation_runs": _REQUIRED_SCHEMA_COLUMNS["world_generation_runs"],
        },
    ),
    (
        _PRE_NOVEL_LANGUAGE_REVISION,
        {
            "auth_identities": _REQUIRED_SCHEMA_COLUMNS["auth_identities"],
            "novels": {
                "language",
                "window_index_status",
                "window_index_revision",
                "window_index_built_revision",
                "window_index_error",
            },
            "chapters": _REQUIRED_SCHEMA_COLUMNS["chapters"],
            "continuation_runs": _REQUIRED_SCHEMA_COLUMNS["continuation_runs"],
            "derived_asset_jobs": _REQUIRED_SCHEMA_COLUMNS["derived_asset_jobs"],
            "novel_ingest_jobs": _REQUIRED_SCHEMA_COLUMNS["novel_ingest_jobs"],
            "world_generation_runs": _REQUIRED_SCHEMA_COLUMNS["world_generation_runs"],
        },
    ),
)


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


def _matching_unversioned_upgrade_baseline(missing_columns: dict[str, set[str]]) -> str | None:
    for baseline_revision, allowed_missing in _UNVERSIONED_AUTO_UPGRADE_BASELINES:
        unexpected_missing = {
            table_name: columns - allowed_missing.get(table_name, set())
            for table_name, columns in missing_columns.items()
            if columns - allowed_missing.get(table_name, set())
        }
        if unexpected_missing:
            continue
        return baseline_revision

    return None


def _revision_number(revision: str | None) -> int | None:
    if revision is None:
        return None
    try:
        return int(revision)
    except (TypeError, ValueError):
        return None


def _recorded_revision(bind) -> str | None:
    try:
        return bind.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    except Exception:
        return None


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
    config = _alembic_config(db_url=db_url, ini_path=ini_path)
    stamp_revision: str | None = None
    should_upgrade = False
    result = "upgraded"

    with db_engine.begin() as bind:
        tables = _user_tables(bind)

        if not _CORE_TABLES.issubset(tables):
            logger.warning(
                "Database missing core selfhost tables; rebuilding current schema and stamping Alembic head."
            )
            _reset_incomplete_bootstrap(bind)
            metadata.create_all(bind=bind)
            stamp_revision = _HEAD_REVISION
            result = "bootstrapped"
        elif "alembic_version" not in tables:
            missing_columns = _missing_required_columns(bind)
            if not missing_columns:
                logger.warning(
                    "Database has current application tables but no alembic_version; stamping Alembic head."
                )
                stamp_revision = _HEAD_REVISION
                result = "stamped"
            else:
                baseline_revision = _matching_unversioned_upgrade_baseline(missing_columns)
                if baseline_revision is None:
                    raise RuntimeError(
                        "Database has application tables but no alembic_version table, and it does not match "
                        "the current schema closely enough to auto-stamp safely. Missing columns: "
                        f"{missing_columns}. Back up the database, then rebuild or migrate it manually."
                    )

                logger.warning(
                    "Database has application tables but no alembic_version; stamping Alembic %s then upgrading "
                    "to head to recover additive schema changes.",
                    baseline_revision,
                )
                stamp_revision = baseline_revision
                should_upgrade = True
        else:
            missing_columns = _missing_required_columns(bind)
            baseline_revision = _matching_unversioned_upgrade_baseline(missing_columns)
            current_revision = _recorded_revision(bind)
            if (
                baseline_revision is not None
                and (baseline_number := _revision_number(baseline_revision)) is not None
                and (current_number := _revision_number(current_revision)) is not None
                and baseline_number > current_number
            ):
                logger.warning(
                    "Database schema already matches additive revision %s while alembic_version is %s; "
                    "stamping forward before upgrade to repair partial migration state.",
                    baseline_revision,
                    current_revision,
                )
                stamp_revision = baseline_revision
            should_upgrade = True

    if stamp_revision is not None:
        stamp(config, stamp_revision)
    if should_upgrade:
        upgrade(config, _HEAD_REVISION)
    return result


def main() -> None:
    ensure_selfhost_database_ready(
        db_engine=engine,
        metadata=Base.metadata,
        db_url=DATABASE_URL,
    )


if __name__ == "__main__":
    main()
