# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import logging
import re
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, defer

from app.core.ingest import inspect_novel_readiness
from app.core.indexing.lifecycle import (
    WindowIndexLifecycleSnapshot,
    inspect_window_index_lifecycle,
)
from app.core.seed_demo import is_seeded_demo_novel
from app.database import DATA_DIR
from app.models import Novel, User
from app.schemas import (
    DerivedAssetJobStatus,
    NovelIngestJobResponse,
    NovelIngestJobStage,
    NovelIngestJobStatus,
    NovelIngestSizeTier,
    NovelResponse,
    WindowIndexCapabilitiesResponse,
    WindowIndexJobResponse,
    WindowIndexJobMetricsResponse,
    WindowIndexLifecycleStatus,
    WindowIndexReadinessStatus,
    WindowIndexStateResponse,
)
from app.config import get_settings

UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)
UPLOAD_CONSENT_VERSION = "2026-03-06"
STREAMING_RESPONSE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Accel-Buffering": "no",
    "X-Content-Type-Options": "nosniff",
}

_SAFE_SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def safe_delete_where(
    db: Session,
    *,
    table: str,
    where_sql: str,
    params: dict[str, Any],
    allow_missing_column: bool = False,
) -> None:
    """Best-effort delete helper for optional/legacy tables."""
    if not _SAFE_SQL_IDENTIFIER_RE.match(table):
        raise ValueError(f"Unsafe table name: {table!r}")

    try:
        with db.begin_nested():
            db.execute(sa.text(f"DELETE FROM {table} WHERE {where_sql}"), params)
    except DBAPIError as exc:
        msg = str(getattr(exc, "orig", exc)).lower()

        if "no such table" in msg:
            logger.debug("Skipping delete from missing table %s", table)
            return
        if allow_missing_column and "no such column" in msg:
            logger.debug("Skipping delete from %s due to missing column", table)
            return

        if "does not exist" in msg and ("relation" in msg or "table" in msg):
            logger.debug("Skipping delete from missing table %s", table)
            return
        if allow_missing_column and "does not exist" in msg and "column" in msg:
            logger.debug("Skipping delete from %s due to missing column", table)
            return

        if "doesn't exist" in msg and "table" in msg:
            logger.debug("Skipping delete from missing table %s", table)
            return
        if allow_missing_column and "unknown column" in msg:
            logger.debug("Skipping delete from %s due to missing column", table)
            return

        raise


def user_novels(db: Session, user: User):
    q = db.query(Novel)
    settings = get_settings()
    if settings.deploy_mode == "selfhost":
        return q
    return q.filter(Novel.owner_id == user.id)


def verify_novel_access(novel: Novel | None, user: User) -> Novel:
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    settings = get_settings()
    if settings.deploy_mode == "hosted" and novel.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Novel not found")
    return novel


def get_accessible_novel(db: Session, novel_id: int, user: User) -> Novel:
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    return verify_novel_access(novel, user)


def fetch_novel_with_presence(db: Session, novel_id: int, user: User) -> tuple[Novel, bool]:
    """Load a novel with the window-index payload deferred plus a presence flag."""
    row = (
        db.query(Novel)
        .options(defer(Novel.window_index))
        .add_columns(novel_window_index_presence_column())
        .filter(Novel.id == novel_id)
        .first()
    )
    novel = verify_novel_access(row[0] if row is not None else None, user)
    return novel, bool(row[1])


def novel_window_index_presence_column():
    return Novel.window_index.is_not(None).label("has_window_index_payload")


def _coerce_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _serialize_window_index_job_metrics(job_snapshot) -> WindowIndexJobMetricsResponse | None:
    raw_metrics = (job_snapshot.result or {}).get("metrics")
    if not isinstance(raw_metrics, dict) or not raw_metrics:
        return None
    metrics = dict(raw_metrics)
    return WindowIndexJobMetricsResponse(
        queue_wait_ms=_coerce_float(metrics.get("queue_wait_ms")),
        load_chapters_ms=_coerce_float(metrics.get("load_chapters_ms")),
        build_artifacts_ms=_coerce_float(metrics.get("build_artifacts_ms")),
        serialize_ms=_coerce_float(metrics.get("serialize_ms")),
        persist_ms=_coerce_float(metrics.get("persist_ms")),
        full_build_ms=_coerce_float(metrics.get("full_build_ms")),
        chapter_count=_coerce_int(metrics.get("chapter_count")),
        chapter_chars=_coerce_int(metrics.get("chapter_chars")),
        payload_bytes=_coerce_int(metrics.get("payload_bytes")),
        rss_kib=_coerce_int(metrics.get("rss_kib")),
        peak_rss_kib=_coerce_int(metrics.get("peak_rss_kib")),
        index_backend=(
            None if metrics.get("index_backend") in (None, "") else str(metrics["index_backend"])
        ),
        executor_backend=(
            None
            if metrics.get("executor_backend") in (None, "")
            else str(metrics["executor_backend"])
        ),
        target_count=_coerce_int(metrics.get("target_count")),
        segment_count=_coerce_int(metrics.get("segment_count")),
        mention_posting_count=_coerce_int(metrics.get("mention_posting_count")),
        claim_atom_count=_coerce_int(metrics.get("claim_atom_count")),
        coverage_rep_count=_coerce_int(metrics.get("coverage_rep_count")),
        discover_targets_ms=_coerce_float(metrics.get("discover_targets_ms")),
        segmentation_ms=_coerce_float(metrics.get("segmentation_ms")),
        mention_ms=_coerce_float(metrics.get("mention_ms")),
        claim_ms=_coerce_float(metrics.get("claim_ms")),
        coverage_ms=_coerce_float(metrics.get("coverage_ms")),
        plan_mode=None if metrics.get("plan_mode") in (None, "") else str(metrics["plan_mode"]),
        incremental_applied=(
            bool(metrics.get("incremental_applied"))
            if metrics.get("incremental_applied") is not None
            else None
        ),
        rebuilt_chapter_count=_coerce_int(metrics.get("rebuilt_chapter_count")),
        reused_chapter_count=_coerce_int(metrics.get("reused_chapter_count")),
        fallback_reason=(
            None if metrics.get("fallback_reason") in (None, "") else str(metrics["fallback_reason"])
        ),
    )


def serialize_novel(
    novel: Novel,
    *,
    index_state: WindowIndexLifecycleSnapshot,
    readiness_state,
) -> NovelResponse:
    job_response = None
    if index_state.job is not None:
        job_response = WindowIndexJobResponse(
            status=DerivedAssetJobStatus(index_state.job.status),
            target_revision=index_state.job.target_revision,
            completed_revision=index_state.job.completed_revision,
            error=index_state.job.error,
            created_at=index_state.job.created_at,
            started_at=index_state.job.started_at,
            finished_at=index_state.job.finished_at,
            metrics=_serialize_window_index_job_metrics(index_state.job),
        )
    ingest_response = None
    if readiness_state.ingest_job is not None:
        ingest_response = NovelIngestJobResponse(
            status=NovelIngestJobStatus(readiness_state.ingest_job.status),
            stage=NovelIngestJobStage(readiness_state.ingest_job.stage),
            size_tier=(
                NovelIngestSizeTier(readiness_state.ingest_job.size_tier)
                if readiness_state.ingest_job.size_tier
                else None
            ),
            source_bytes=readiness_state.ingest_job.source_bytes,
            source_chars=readiness_state.ingest_job.source_chars,
            chapter_count=readiness_state.ingest_job.chapter_count,
            requested_language=readiness_state.ingest_job.requested_language,
            resolved_language=readiness_state.ingest_job.resolved_language,
            auto_index_plan=readiness_state.ingest_job.auto_index_plan,
            bootstrap_plan=readiness_state.ingest_job.bootstrap_plan,
            readiness_mode=readiness_state.ingest_job.readiness_mode,
            error=readiness_state.ingest_job.error,
        )
    return NovelResponse(
        id=novel.id,
        title=novel.title,
        author=novel.author,
        language=novel.language,
        total_chapters=novel.total_chapters,
        is_seeded_demo=is_seeded_demo_novel(novel),
        window_index=WindowIndexStateResponse(
            status=WindowIndexLifecycleStatus(index_state.status),
            revision=index_state.revision,
            built_revision=index_state.built_revision,
            error=index_state.error,
            readiness=WindowIndexReadinessStatus(readiness_state.readiness),
            capabilities=WindowIndexCapabilitiesResponse(
                chapters_available=readiness_state.capabilities.chapters_available,
                whole_book_index_available=readiness_state.capabilities.whole_book_index_available,
                bootstrap_available=readiness_state.capabilities.bootstrap_available,
                recent_fallback_only=readiness_state.capabilities.recent_fallback_only,
            ),
            ingest=ingest_response,
            job=job_response,
        ),
        created_at=novel.created_at,
        updated_at=novel.updated_at,
    )


def serialize_novel_with_states(
    novel: Novel,
    *,
    db: Session,
    has_window_index_payload: bool,
) -> NovelResponse:
    """Resolve index/readiness states for one novel and serialize it."""
    index_state = inspect_window_index_lifecycle(
        novel,
        db=db,
        has_payload_override=has_window_index_payload,
    )
    readiness_state = inspect_novel_readiness(
        novel,
        db=db,
        index_state=index_state,
    )
    return serialize_novel(novel, index_state=index_state, readiness_state=readiness_state)
