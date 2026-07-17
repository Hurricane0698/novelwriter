# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any, Callable, Iterable, Mapping

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.derived_assets import (
    DERIVED_ASSET_JOB_STATUS_QUEUED,
    DERIVED_ASSET_JOB_STATUS_RUNNING,
    DERIVED_ASSET_KIND_WINDOW_INDEX,
    DerivedAssetJobSnapshot,
    DerivedAssetPersistResult,
    enqueue_derived_asset_job,
    inspect_derived_asset_job,
    inspect_derived_asset_jobs,
    run_derived_asset_job_until_idle,
)
from app.config import Settings, get_settings
from app.core.job_runtime import stale_running_job_filter, utcnow_naive
from app.core.world.bootstrap_queue import ensure_ingest_bootstrap_job
from app.models import DerivedAssetJob
from app.models import Novel

from .artifact_store import (
    persist_window_index_build_failure,
    persist_window_index_build_success,
)
from .chapters import load_chapter_texts
from .state_proto_executor import execute_state_proto_build
from .state_proto_model import StateProtoBuildOutput
from .state_proto_targets import load_state_proto_target_specs

WINDOW_INDEX_STATUS_MISSING = "missing"
WINDOW_INDEX_STATUS_STALE = "stale"
WINDOW_INDEX_STATUS_FRESH = "fresh"
WINDOW_INDEX_STATUS_FAILED = "failed"
KNOWN_WINDOW_INDEX_STATUSES = frozenset(
    {
        WINDOW_INDEX_STATUS_MISSING,
        WINDOW_INDEX_STATUS_STALE,
        WINDOW_INDEX_STATUS_FRESH,
        WINDOW_INDEX_STATUS_FAILED,
    }
)
WINDOW_INDEX_REBUILD_FAILED_MESSAGE = "窗口索引重建失败，请稍后重试"

WINDOW_INDEX_JOB_RESULT_STATE_KEY = "asset_state"
WINDOW_INDEX_JOB_METRICS_KEY = "metrics"

logger = logging.getLogger(__name__)


def _round_ms(value: float | None) -> float | None:
    if value is None:
        return None
    return round(max(float(value), 0.0), 1)


def _build_window_index_job_metrics(
    *,
    build_output: StateProtoBuildOutput,
    queue_wait_ms: float | None,
    full_build_ms: float | None,
) -> dict[str, Any]:
    load_chapters_ms = _round_ms(getattr(build_output, "load_chapters_ms", 0.0))
    build_artifacts_ms = _round_ms(
        (getattr(build_output, "segmentation_ms", 0.0) or 0.0)
        + (getattr(build_output, "discover_targets_ms", 0.0) or 0.0)
        + (getattr(build_output, "mention_ms", 0.0) or 0.0)
        + (getattr(build_output, "claim_ms", 0.0) or 0.0)
        + (getattr(build_output, "coverage_ms", 0.0) or 0.0)
    )
    serialize_ms = _round_ms(getattr(build_output, "serialize_ms", 0.0))
    persist_ms = None
    if full_build_ms is not None:
        accounted_ms = (load_chapters_ms or 0.0) + (getattr(build_output, "duration_ms", 0.0) or 0.0)
        persist_ms = _round_ms(full_build_ms - accounted_ms)
    metrics = {
        "queue_wait_ms": _round_ms(queue_wait_ms),
        "load_chapters_ms": load_chapters_ms,
        "build_artifacts_ms": build_artifacts_ms,
        "serialize_ms": serialize_ms,
        "persist_ms": persist_ms,
        "full_build_ms": _round_ms(full_build_ms),
        "chapter_count": int(build_output.chapter_count or 0),
        "chapter_chars": int(build_output.chapter_chars or 0),
        "payload_bytes": int(build_output.payload_bytes or 0),
        "rss_kib": build_output.rss_kib,
        "peak_rss_kib": build_output.peak_rss_kib,
        "index_backend": "state_proto_v2",
        "executor_backend": getattr(build_output, "executor_backend", "none"),
        "target_count": int(build_output.target_count or 0),
        "segment_count": int(build_output.segment_count or 0),
        "mention_posting_count": int(build_output.mention_posting_count or 0),
        "claim_atom_count": int(build_output.claim_atom_count or 0),
        "coverage_rep_count": int(build_output.coverage_rep_count or 0),
        "discover_targets_ms": _round_ms(build_output.discover_targets_ms),
        "segmentation_ms": _round_ms(build_output.segmentation_ms),
        "mention_ms": _round_ms(build_output.mention_ms),
        "claim_ms": _round_ms(build_output.claim_ms),
        "coverage_ms": _round_ms(build_output.coverage_ms),
        "plan_mode": build_output.plan_mode,
        "incremental_applied": bool(build_output.incremental_applied),
        "rebuilt_chapter_count": int(build_output.rebuilt_chapter_count or 0),
        "reused_chapter_count": int(build_output.reused_chapter_count or 0),
        "fallback_reason": build_output.fallback_reason,
    }
    return metrics


def normalize_window_index_status(raw_status: str | None, *, has_payload: bool) -> str:
    value = (raw_status or "").strip().lower()
    if value in KNOWN_WINDOW_INDEX_STATUSES:
        return value
    return WINDOW_INDEX_STATUS_FRESH if has_payload else WINDOW_INDEX_STATUS_MISSING


def resolve_window_index_target_revision(
    novel: Novel,
    *,
    has_source_text: bool,
) -> int:
    current_revision = max(
        int(getattr(novel, "window_index_revision", 0) or 0),
        int(getattr(novel, "window_index_built_revision", 0) or 0),
        0,
    )
    if has_source_text and current_revision <= 0:
        return 1
    return current_revision


def mark_window_index_inputs_changed(novel: Novel) -> int:
    new_revision = resolve_window_index_target_revision(
        novel,
        has_source_text=bool(getattr(novel, "window_index_revision", 0) or getattr(novel, "window_index_built_revision", 0)),
    ) + 1
    novel.window_index_revision = new_revision
    novel.window_index_error = None
    if getattr(novel, "window_index_built_revision", None) is not None:
        # Keep the last successful payload as the worker-only incremental base.
        # Readiness still stays stale, so product/runtime paths do not treat it
        # as a fresh whole-book index while a rebuild is pending.
        novel.window_index_status = WINDOW_INDEX_STATUS_STALE
    else:
        novel.window_index = None
        novel.window_index_status = WINDOW_INDEX_STATUS_MISSING
    return new_revision


def mark_window_index_missing(novel: Novel, *, revision: int | None = None) -> int:
    target_revision = max(
        int(revision if revision is not None else getattr(novel, "window_index_revision", 0) or 0),
        0,
    )
    novel.window_index_revision = target_revision
    novel.window_index_status = WINDOW_INDEX_STATUS_MISSING
    novel.window_index = None
    novel.window_index_error = None
    return target_revision


def mark_window_index_build_succeeded(
    novel: Novel,
    *,
    index_payload: bytes,
    revision: int | None = None,
) -> int:
    target_revision = max(
        int(revision if revision is not None else getattr(novel, "window_index_revision", 0) or 0),
        1,
    )
    novel.window_index_revision = target_revision
    novel.window_index_built_revision = target_revision
    novel.window_index_status = WINDOW_INDEX_STATUS_FRESH
    novel.window_index = index_payload
    novel.window_index_error = None
    return target_revision


def mark_window_index_build_failed(
    novel: Novel,
    *,
    error: str,
    revision: int | None = None,
) -> int:
    target_revision = max(
        int(revision if revision is not None else getattr(novel, "window_index_revision", 0) or 0),
        1,
    )
    novel.window_index_revision = target_revision
    novel.window_index_status = WINDOW_INDEX_STATUS_FAILED
    novel.window_index = None
    novel.window_index_error = error
    return target_revision

class WindowIndexLifecycleSnapshot:
    __slots__ = ("status", "revision", "built_revision", "error", "has_payload", "job")

    def __init__(
        self,
        *,
        status: str,
        revision: int,
        built_revision: int | None,
        error: str | None,
        has_payload: bool,
        job: DerivedAssetJobSnapshot | None = None,
    ) -> None:
        self.status = status
        self.revision = revision
        self.built_revision = built_revision
        self.error = error
        self.has_payload = has_payload
        self.job = job


def _stale_window_index_job_filter(now, settings: Settings):
    return stale_running_job_filter(
        DerivedAssetJob,
        now=now,
        stale_timeout_seconds=int(settings.derived_asset_job_stale_timeout_seconds or 0),
    )


def select_next_window_index_rebuild_job_novel_id(
    *,
    session_factory: Callable[[], Session],
    settings: Settings | None = None,
) -> int | None:
    resolved_settings = settings or get_settings()
    db = session_factory()
    try:
        now = utcnow_naive()
        row = (
            db.query(DerivedAssetJob.novel_id)
            .filter(
                DerivedAssetJob.asset_kind == DERIVED_ASSET_KIND_WINDOW_INDEX,
                or_(
                    DerivedAssetJob.status == DERIVED_ASSET_JOB_STATUS_QUEUED,
                    and_(
                        DerivedAssetJob.status == DERIVED_ASSET_JOB_STATUS_RUNNING,
                        _stale_window_index_job_filter(now, resolved_settings),
                    ),
                ),
            )
            .order_by(DerivedAssetJob.created_at.asc(), DerivedAssetJob.id.asc())
            .first()
        )
        if row is None:
            return None
        return int(row[0])
    finally:
        db.close()


def run_next_window_index_rebuild_job(
    *,
    session_factory: Callable[[], Session],
    settings: Settings | None = None,
) -> bool:
    resolved_settings = settings or get_settings()
    novel_id = select_next_window_index_rebuild_job_novel_id(
        session_factory=session_factory,
        settings=resolved_settings,
    )
    if novel_id is None:
        return False
    run_derived_asset_job_until_idle(
        novel_id=novel_id,
        adapter=WINDOW_INDEX_JOB_ADAPTER,
        session_factory=session_factory,
        settings=resolved_settings,
    )
    ensure_ingest_bootstrap_job(
        novel_id,
        session_factory=session_factory,
        settings=resolved_settings,
    )
    return True


def inspect_window_index_lifecycle(
    novel: Novel,
    *,
    db: Session | None = None,
    has_payload_override: bool | None = None,
) -> WindowIndexLifecycleSnapshot:
    job_snapshot = None
    novel_id = getattr(novel, "id", None)
    if db is not None and isinstance(novel_id, int):
        job_snapshot = inspect_window_index_rebuild_job(db, novel_id=novel_id)
    return _build_window_index_lifecycle_snapshot(
        novel,
        job_snapshot=job_snapshot,
        has_payload_override=has_payload_override,
    )


def _build_window_index_lifecycle_snapshot(
    novel: Novel,
    *,
    job_snapshot: DerivedAssetJobSnapshot | None = None,
    has_payload_override: bool | None = None,
) -> WindowIndexLifecycleSnapshot:
    has_payload = (
        bool(has_payload_override)
        if has_payload_override is not None
        else bool(getattr(novel, "window_index", None))
    )
    built_revision = getattr(novel, "window_index_built_revision", None)
    normalized_status = normalize_window_index_status(
        getattr(novel, "window_index_status", None),
        has_payload=has_payload,
    )
    return WindowIndexLifecycleSnapshot(
        status=normalized_status,
        revision=int(getattr(novel, "window_index_revision", 0) or 0),
        built_revision=int(built_revision) if built_revision is not None else None,
        error=getattr(novel, "window_index_error", None),
        has_payload=has_payload,
        job=job_snapshot,
    )


def inspect_window_index_lifecycles(
    novels: Iterable[Novel],
    *,
    db: Session | None = None,
    has_payload_overrides: Mapping[int, bool] | None = None,
) -> dict[int, WindowIndexLifecycleSnapshot]:
    novel_list = list(novels)
    if not novel_list:
        return {}

    job_snapshots: dict[int, DerivedAssetJobSnapshot] = {}
    if db is not None:
        job_snapshots = inspect_window_index_rebuild_jobs(
            db,
            novel_ids=[
                novel_id
                for novel in novel_list
                if isinstance((novel_id := getattr(novel, "id", None)), int)
            ],
        )

    return {
        novel_id: _build_window_index_lifecycle_snapshot(
            novel,
            job_snapshot=job_snapshots.get(novel_id),
            has_payload_override=(
                bool(has_payload_overrides[novel_id])
                if has_payload_overrides is not None and novel_id in has_payload_overrides
                else None
            ),
        )
        for novel in novel_list
        if isinstance((novel_id := getattr(novel, "id", None)), int)
    }


class _WindowIndexJobAdapter:
    asset_kind = DERIVED_ASSET_KIND_WINDOW_INDEX

    def build(
        self,
        *,
        novel_id: int,
        target_revision: int,
        session_factory: Callable[[], Session],
        settings: Settings,
    ) -> StateProtoBuildOutput:
        db = session_factory()
        try:
            novel = db.query(Novel).filter(Novel.id == novel_id).first()
            if novel is None:
                return StateProtoBuildOutput(
                    asset_state=WINDOW_INDEX_STATUS_MISSING,
                    executor_backend="none",
                )
            load_started_at = perf_counter()
            chapters = load_chapter_texts(db, novel_id)
            novel_language = getattr(novel, "language", None)
            target_specs = load_state_proto_target_specs(db, novel_id)
            existing_payload = getattr(novel, "window_index", None)
            load_chapters_ms = round((perf_counter() - load_started_at) * 1000, 1)
        finally:
            db.close()
        logger.info(
            "window_index: state-proto build started "
            "novel=%s revision=%s chapters=%s chars=%s target_specs=%s existing_payload_bytes=%s",
            novel_id,
            target_revision,
            len(chapters),
            sum(len(getattr(chapter, "text", "") or "") for chapter in chapters),
            len(target_specs),
            len(existing_payload) if existing_payload else 0,
        )
        build_output = execute_state_proto_build(
            chapters=chapters,
            novel_language=novel_language,
            target_specs=target_specs,
            existing_payload=existing_payload,
            settings=settings,
        )
        logger.info(
            "window_index: state-proto build completed "
            "novel=%s revision=%s state=%s backend=%s plan=%s "
            "chapters=%s chars=%s targets=%s segments=%s mentions=%s claims=%s coverage=%s "
            "rebuilt=%s reused=%s payload_bytes=%s "
            "load_ms=%.1f discover_ms=%.1f segmentation_ms=%.1f mention_ms=%.1f "
            "claim_ms=%.1f coverage_ms=%.1f serialize_ms=%.1f duration_ms=%.1f "
            "rss_kib=%s peak_rss_kib=%s",
            novel_id,
            target_revision,
            build_output.asset_state,
            getattr(build_output, "executor_backend", "none"),
            getattr(build_output, "plan_mode", "full"),
            build_output.chapter_count,
            build_output.chapter_chars,
            getattr(build_output, "target_count", 0),
            getattr(build_output, "segment_count", 0),
            getattr(build_output, "mention_posting_count", 0),
            getattr(build_output, "claim_atom_count", 0),
            getattr(build_output, "coverage_rep_count", 0),
            int(getattr(build_output, "rebuilt_chapter_count", 0) or 0),
            int(getattr(build_output, "reused_chapter_count", 0) or 0),
            build_output.payload_bytes,
            load_chapters_ms,
            getattr(build_output, "discover_targets_ms", 0.0),
            getattr(build_output, "segmentation_ms", 0.0),
            getattr(build_output, "mention_ms", 0.0),
            getattr(build_output, "claim_ms", 0.0),
            getattr(build_output, "coverage_ms", 0.0),
            build_output.serialize_ms,
            build_output.duration_ms,
            build_output.rss_kib,
            build_output.peak_rss_kib,
            extra={
                "novel_id": novel_id,
                "target_revision": target_revision,
                "asset_state": build_output.asset_state,
                "chapter_count": build_output.chapter_count,
                "chapter_chars": build_output.chapter_chars,
                "executor_backend": getattr(build_output, "executor_backend", "none"),
                "target_count": getattr(build_output, "target_count", 0),
                "segment_count": getattr(build_output, "segment_count", 0),
                "mention_posting_count": getattr(build_output, "mention_posting_count", 0),
                "claim_atom_count": getattr(build_output, "claim_atom_count", 0),
                "coverage_rep_count": getattr(build_output, "coverage_rep_count", 0),
                "payload_bytes": build_output.payload_bytes,
                "load_chapters_ms": load_chapters_ms,
                "plan_mode": getattr(build_output, "plan_mode", "full"),
                "incremental_applied": bool(getattr(build_output, "incremental_applied", False)),
                "rebuilt_chapter_count": int(getattr(build_output, "rebuilt_chapter_count", 0) or 0),
                "reused_chapter_count": int(getattr(build_output, "reused_chapter_count", 0) or 0),
                "segmentation_ms": getattr(build_output, "segmentation_ms", 0.0),
                "discover_targets_ms": getattr(build_output, "discover_targets_ms", 0.0),
                "mention_ms": getattr(build_output, "mention_ms", 0.0),
                "claim_ms": getattr(build_output, "claim_ms", 0.0),
                "coverage_ms": getattr(build_output, "coverage_ms", 0.0),
                "serialize_ms": build_output.serialize_ms,
                "duration_ms": build_output.duration_ms,
                "rss_kib": build_output.rss_kib,
                "peak_rss_kib": build_output.peak_rss_kib,
            },
        )
        build_output.load_chapters_ms = load_chapters_ms
        return build_output

    def persist_success(
        self,
        *,
        db: Session,
        job,
        target_revision: int,
        claim,
        finished_at,
        build_output: StateProtoBuildOutput,
    ) -> DerivedAssetPersistResult:
        novel = db.query(Novel).filter(Novel.id == job.novel_id).first()
        if novel is None:
            return DerivedAssetPersistResult(superseded=True)

        current_revision = int(getattr(novel, "window_index_revision", 0) or 0)
        if current_revision > target_revision:
            return DerivedAssetPersistResult(
                superseded=True,
                next_target_revision=current_revision,
            )

        target = max(target_revision, current_revision, 1)
        full_build_ms = round(max((finished_at - claim.started_at).total_seconds() * 1000, 0.0), 1)
        return persist_window_index_build_success(
            novel,
            target_revision=target,
            asset_state=build_output.asset_state,
            index_payload=build_output.index_payload,
            result={
                WINDOW_INDEX_JOB_METRICS_KEY: _build_window_index_job_metrics(
                    build_output=build_output,
                    queue_wait_ms=claim.queue_wait_ms,
                    full_build_ms=full_build_ms,
                ),
            },
        )

    def persist_failure(
        self,
        *,
        db: Session,
        job,
        target_revision: int,
        error: str,
    ) -> bool:
        novel = db.query(Novel).filter(Novel.id == job.novel_id).first()
        if novel is None:
            return True

        current_revision = int(getattr(novel, "window_index_revision", 0) or 0)
        if current_revision > target_revision:
            job.target_revision = max(int(job.target_revision or 0), current_revision)
            return True

        return persist_window_index_build_failure(
            novel,
            target_revision=target_revision,
            current_revision=current_revision,
            error=error,
        )

    def sanitize_error(self, exc: Exception) -> str:
        _ = exc
        return WINDOW_INDEX_REBUILD_FAILED_MESSAGE


WINDOW_INDEX_JOB_ADAPTER = _WindowIndexJobAdapter()


def enqueue_window_index_rebuild_job(
    db: Session,
    *,
    novel_id: int,
    target_revision: int,
    settings: Settings | None = None,
):
    return enqueue_derived_asset_job(
        db,
        novel_id=novel_id,
        asset_kind=DERIVED_ASSET_KIND_WINDOW_INDEX,
        target_revision=target_revision,
        settings=settings,
    )


def inspect_window_index_rebuild_job(
    db: Session,
    *,
    novel_id: int,
) -> DerivedAssetJobSnapshot | None:
    return inspect_derived_asset_job(
        db,
        novel_id=novel_id,
        asset_kind=DERIVED_ASSET_KIND_WINDOW_INDEX,
    )


def inspect_window_index_rebuild_jobs(
    db: Session,
    *,
    novel_ids: Iterable[int],
) -> dict[int, DerivedAssetJobSnapshot]:
    return inspect_derived_asset_jobs(
        db,
        novel_ids=novel_ids,
        asset_kind=DERIVED_ASSET_KIND_WINDOW_INDEX,
    )


def enqueue_window_index_rebuild_for_latest_revision(
    novel_id: int,
    *,
    session_factory: Callable[[], Session],
    settings: Settings | None = None,
) -> int | None:
    resolved_settings = settings or get_settings()
    db = session_factory()
    try:
        novel = db.query(Novel).filter(Novel.id == novel_id).first()
        if novel is None:
            return None
        chapters = load_chapter_texts(db, novel_id)
        target_revision = resolve_window_index_target_revision(
            novel,
            has_source_text=bool(chapters),
        )
        enqueue_window_index_rebuild_job(
            db,
            novel_id=novel_id,
            target_revision=target_revision,
            settings=resolved_settings,
        )
        db.commit()
        return target_revision
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
