from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Callable

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.core.derived_assets import (
    DERIVED_ASSET_JOB_STATUS_COMPLETED,
    DERIVED_ASSET_JOB_STATUS_FAILED,
    DERIVED_ASSET_JOB_STATUS_RUNNING,
    DERIVED_ASSET_KIND_WINDOW_INDEX,
)
from app.core.job_runtime import (
    apply_row_updates,
    refresh_lease_values,
    release_lease_values,
    run_job_until_idle,
    stale_running_job_filter,
    utcnow_naive,
)
from app.core.indexing.lifecycle import enqueue_window_index_rebuild_job
from app.core.indexing.planner import AUTO_INDEX_PLAN_DEFERRED
from app.core.world.bootstrap_queue import ensure_ingest_bootstrap_job
from app.models import DerivedAssetJob, Novel, NovelIngestJob
from app.core.source_errors import (
    MarkdownStructureInvalidError,
    SourceEncodingUnsupportedError,
)

from .contracts import IngestPolicyDecision, IngestPolicyInput, ParsedNovelIngest
from .job_store import (
    INGEST_JOB_STAGE_COMPLETED,
    INGEST_JOB_STAGE_DECODING,
    INGEST_JOB_STAGE_FAILED,
    INGEST_JOB_STAGE_PARSING,
    INGEST_JOB_STAGE_PERSISTING,
    INGEST_JOB_STAGE_PLANNING,
    INGEST_JOB_STATUS_COMPLETED,
    INGEST_JOB_STATUS_FAILED,
    INGEST_JOB_STATUS_QUEUED,
    INGEST_JOB_STATUS_RUNNING,
    claim_novel_ingest_job,
    select_next_novel_ingest_job_novel_id,
)
from .parser_service import parse_source_file
from .persistence import persist_ingest_success
from .policy import resolve_ingest_policy

logger = logging.getLogger(__name__)

INGEST_SOURCE_MISSING_MESSAGE = "上传源文件不存在，请重新上传"
INGEST_SOURCE_ENCODING_UNSUPPORTED_MESSAGE = "文件编码不受支持；Markdown 请使用 UTF-8 或 UTF-8 BOM"
INGEST_MARKDOWN_STRUCTURE_INVALID_MESSAGE = "Markdown 结构无效；请按 # 卷名、## 章节名整理后重新上传"
INGEST_JOB_FAILED_MESSAGE = "稿件导入失败，请稍后重试"

INGEST_ERROR_SOURCE_MISSING = "source_missing"
INGEST_ERROR_SOURCE_ENCODING_UNSUPPORTED = "source_encoding_unsupported"
INGEST_ERROR_MARKDOWN_STRUCTURE_INVALID = "markdown_structure_invalid"
INGEST_ERROR_INTERNAL = "ingest_internal_error"


@dataclass(frozen=True, slots=True)
class _NovelIngestBuildOutput:
    parsed: ParsedNovelIngest
    decision: IngestPolicyDecision


def _touch_stage(
    *,
    job_id: int,
    worker_id: str,
    stage: str,
    session_factory: Callable[[], Session],
    settings: Settings,
) -> None:
    db = session_factory()
    try:
        now = utcnow_naive()
        db.query(NovelIngestJob).filter(
            NovelIngestJob.id == job_id,
            NovelIngestJob.status == INGEST_JOB_STATUS_RUNNING,
            NovelIngestJob.lease_owner == worker_id,
        ).update(
            refresh_lease_values(
                NovelIngestJob,
                now=now,
                lease_seconds=int(settings.ingest_job_lease_seconds or 0),
                extra_updates={NovelIngestJob.stage: stage},
            ),
            synchronize_session=False,
        )
        db.commit()
    finally:
        db.close()


def _finalize_ingest_job(
    *,
    claim,
    session_factory: Callable[[], Session],
    status: str,
    stage: str,
    error: str | None,
    persist: Callable[[Session, NovelIngestJob], bool] | None = None,
) -> None:
    """Release the lease and finalize the claimed job row.

    `persist` runs after the lease-ownership guard; returning False aborts
    without finalizing (e.g. the novel disappeared mid-job).
    """
    db = session_factory()
    try:
        job = db.query(NovelIngestJob).filter(NovelIngestJob.id == claim.job_id).first()
        if job is None:
            return
        if job.status != INGEST_JOB_STATUS_RUNNING or job.lease_owner != claim.worker_id:
            return
        if persist is not None and not persist(db, job):
            return

        now = utcnow_naive()
        apply_row_updates(
            job,
            release_lease_values(
                NovelIngestJob,
                now=now,
                extra_updates={
                    NovelIngestJob.status: status,
                    NovelIngestJob.stage: stage,
                    NovelIngestJob.error: error,
                    NovelIngestJob.finished_at: now,
                },
            ),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _load_novel_ingest_inputs(
    *,
    claim,
    session_factory: Callable[[], Session],
) -> tuple[str, str, str | None, int]:
    db = session_factory()
    try:
        job = db.query(NovelIngestJob).filter(NovelIngestJob.id == claim.job_id).first()
        novel = db.query(Novel).filter(Novel.id == claim.novel_id).first()
        if job is None or novel is None:
            raise FileNotFoundError("ingest job or novel missing")
        return (
            str(novel.file_path),
            str(novel.content_format),
            job.requested_language,
            int(job.source_bytes or 0),
        )
    finally:
        db.close()


def _sanitize_ingest_error(exc: Exception) -> str:
    if isinstance(exc, FileNotFoundError):
        return INGEST_SOURCE_MISSING_MESSAGE
    if isinstance(exc, SourceEncodingUnsupportedError):
        return INGEST_SOURCE_ENCODING_UNSUPPORTED_MESSAGE
    if isinstance(exc, MarkdownStructureInvalidError):
        return INGEST_MARKDOWN_STRUCTURE_INVALID_MESSAGE
    return INGEST_JOB_FAILED_MESSAGE


def _ingest_error_code(error: str) -> str:
    return {
        INGEST_SOURCE_MISSING_MESSAGE: INGEST_ERROR_SOURCE_MISSING,
        INGEST_SOURCE_ENCODING_UNSUPPORTED_MESSAGE: INGEST_ERROR_SOURCE_ENCODING_UNSUPPORTED,
        INGEST_MARKDOWN_STRUCTURE_INVALID_MESSAGE: INGEST_ERROR_MARKDOWN_STRUCTURE_INVALID,
        INGEST_JOB_FAILED_MESSAGE: INGEST_ERROR_INTERNAL,
    }[error]


class _NovelIngestRuntimeAdapter:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings

    def build(self, *, claim) -> _NovelIngestBuildOutput:
        _touch_stage(
            job_id=claim.job_id,
            worker_id=claim.worker_id,
            stage=INGEST_JOB_STAGE_DECODING,
            session_factory=self._session_factory,
            settings=self._settings,
        )
        file_path, content_format, requested_language, source_bytes = _load_novel_ingest_inputs(
            claim=claim,
            session_factory=self._session_factory,
        )
        _touch_stage(
            job_id=claim.job_id,
            worker_id=claim.worker_id,
            stage=INGEST_JOB_STAGE_PARSING,
            session_factory=self._session_factory,
            settings=self._settings,
        )
        parsed = parse_source_file(
            file_path,
            content_format=content_format,
            requested_language=requested_language,
        )
        _touch_stage(
            job_id=claim.job_id,
            worker_id=claim.worker_id,
            stage=INGEST_JOB_STAGE_PLANNING,
            session_factory=self._session_factory,
            settings=self._settings,
        )
        decision = resolve_ingest_policy(
            IngestPolicyInput(
                source_bytes=source_bytes,
                source_chars=int(parsed.source_chars),
                chapter_count=len(parsed.chapters),
            ),
            settings=self._settings,
        )
        _touch_stage(
            job_id=claim.job_id,
            worker_id=claim.worker_id,
            stage=INGEST_JOB_STAGE_PERSISTING,
            session_factory=self._session_factory,
            settings=self._settings,
        )
        return _NovelIngestBuildOutput(parsed=parsed, decision=decision)

    def finalize_success(
        self,
        *,
        claim,
        build_output: _NovelIngestBuildOutput,
    ) -> bool:
        def _persist(db: Session, job: NovelIngestJob) -> bool:
            novel = db.query(Novel).filter(Novel.id == claim.novel_id).first()
            if novel is None:
                return False
            persist_ingest_success(
                db,
                novel=novel,
                job=job,
                parsed=build_output.parsed,
                decision=build_output.decision,
            )
            return True

        _finalize_ingest_job(
            claim=claim,
            session_factory=self._session_factory,
            status=INGEST_JOB_STATUS_COMPLETED,
            stage=INGEST_JOB_STAGE_COMPLETED,
            error=None,
            persist=_persist,
        )
        ensure_ingest_bootstrap_job(
            claim.novel_id,
            session_factory=self._session_factory,
            settings=self._settings,
        )
        return False

    def finalize_failure(self, *, claim, error: str) -> bool:
        error_code = _ingest_error_code(error)

        def _persist_error_code(_db: Session, job: NovelIngestJob) -> bool:
            job.error_code = error_code
            return True

        _finalize_ingest_job(
            claim=claim,
            session_factory=self._session_factory,
            status=INGEST_JOB_STATUS_FAILED,
            stage=INGEST_JOB_STAGE_FAILED,
            error=error,
            persist=_persist_error_code,
        )
        return False

    def sanitize_error(self, exc: Exception) -> str:
        return _sanitize_ingest_error(exc)

    def format_failure(self, claim) -> str:
        return f"ingest[{claim.job_id}]: job failed for novel {claim.novel_id}"


def run_novel_ingest_job_until_idle(
    *,
    novel_id: int,
    session_factory: Callable[[], Session],
    settings: Settings | None = None,
) -> bool:
    resolved_settings = settings or get_settings()
    return run_job_until_idle(
        claim_next=lambda worker_id: claim_novel_ingest_job(
            novel_id=novel_id,
            session_factory=session_factory,
            worker_id=worker_id,
            settings=resolved_settings,
        ),
        adapter=_NovelIngestRuntimeAdapter(
            session_factory=session_factory,
            settings=resolved_settings,
        ),
        logger=logger,
    )


def run_next_novel_ingest_job(
    *,
    session_factory: Callable[[], Session],
    settings: Settings | None = None,
) -> bool:
    novel_id = select_next_novel_ingest_job_novel_id(
        session_factory=session_factory,
        settings=settings,
    )
    if novel_id is None:
        return False
    run_novel_ingest_job_until_idle(
        novel_id=novel_id,
        session_factory=session_factory,
        settings=settings,
    )
    return True


def enqueue_next_deferred_window_index_build(
    *,
    session_factory: Callable[[], Session],
    settings: Settings | None = None,
) -> bool:
    resolved_settings = settings or get_settings()
    db = session_factory()
    try:
        now = utcnow_naive()
        pending_ingest = (
            db.query(NovelIngestJob.id)
            .filter(
                or_(
                    NovelIngestJob.status == INGEST_JOB_STATUS_QUEUED,
                    and_(
                        NovelIngestJob.status == INGEST_JOB_STATUS_RUNNING,
                        stale_running_job_filter(
                            NovelIngestJob,
                            now=now,
                            stale_timeout_seconds=int(
                                resolved_settings.ingest_job_stale_timeout_seconds or 0
                            ),
                        ),
                    ),
                )
            )
            .first()
        )
        if pending_ingest is not None:
            return False

        row = (
            db.query(
                NovelIngestJob.novel_id,
                Novel.window_index_revision,
            )
            .join(Novel, Novel.id == NovelIngestJob.novel_id)
            .outerjoin(
                DerivedAssetJob,
                and_(
                    DerivedAssetJob.novel_id == NovelIngestJob.novel_id,
                    DerivedAssetJob.asset_kind == DERIVED_ASSET_KIND_WINDOW_INDEX,
                ),
            )
            .filter(
                NovelIngestJob.status == INGEST_JOB_STATUS_COMPLETED,
                NovelIngestJob.auto_index_plan == AUTO_INDEX_PLAN_DEFERRED,
                Novel.total_chapters > 0,
                Novel.window_index_revision > func.coalesce(Novel.window_index_built_revision, 0),
                or_(
                    DerivedAssetJob.id.is_(None),
                    DerivedAssetJob.status == DERIVED_ASSET_JOB_STATUS_FAILED,
                    and_(
                        DerivedAssetJob.status == DERIVED_ASSET_JOB_STATUS_COMPLETED,
                        func.coalesce(DerivedAssetJob.completed_revision, 0) < Novel.window_index_revision,
                    ),
                    and_(
                        DerivedAssetJob.status == DERIVED_ASSET_JOB_STATUS_RUNNING,
                        stale_running_job_filter(
                            DerivedAssetJob,
                            now=now,
                            stale_timeout_seconds=int(
                                resolved_settings.derived_asset_job_stale_timeout_seconds or 0
                            ),
                        ),
                    ),
                ),
            )
            .order_by(NovelIngestJob.finished_at.asc(), NovelIngestJob.id.asc())
            .first()
        )
        if row is None:
            return False

        novel_id, target_revision = int(row[0]), int(row[1] or 0)
        enqueue_window_index_rebuild_job(
            db,
            novel_id=novel_id,
            target_revision=target_revision,
            settings=resolved_settings,
        )
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
