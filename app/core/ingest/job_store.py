from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.core.job_runtime import (
    claim_lease_values,
    is_stale_running_job,
    normalize_utc_naive,
    stale_running_job_filter,
    utcnow_naive,
)
from app.models import NovelIngestJob

INGEST_JOB_STATUS_QUEUED = "queued"
INGEST_JOB_STATUS_RUNNING = "running"
INGEST_JOB_STATUS_COMPLETED = "completed"
INGEST_JOB_STATUS_FAILED = "failed"

INGEST_JOB_STAGE_ACCEPTED = "accepted"
INGEST_JOB_STAGE_DECODING = "decoding"
INGEST_JOB_STAGE_PARSING = "parsing"
INGEST_JOB_STAGE_PERSISTING = "persisting"
INGEST_JOB_STAGE_PLANNING = "planning"
INGEST_JOB_STAGE_COMPLETED = "completed"
INGEST_JOB_STAGE_FAILED = "failed"


@dataclass(frozen=True, slots=True)
class NovelIngestJobSnapshot:
    job_id: int
    novel_id: int
    status: str
    stage: str
    size_tier: str | None
    source_bytes: int
    source_chars: int | None
    chapter_count: int | None
    requested_language: str | None
    resolved_language: str | None
    auto_index_plan: str | None
    bootstrap_plan: str | None
    readiness_mode: str | None
    error: str | None
    lease_owner: str | None
    lease_expires_at: object | None
    started_at: object | None
    finished_at: object | None
    created_at: object | None
    updated_at: object | None


@dataclass(frozen=True, slots=True)
class _NovelIngestClaim:
    job_id: int
    novel_id: int
    worker_id: str


def serialize_novel_ingest_job(job: NovelIngestJob) -> NovelIngestJobSnapshot:
    return NovelIngestJobSnapshot(
        job_id=int(job.id),
        novel_id=int(job.novel_id),
        status=job.status,
        stage=job.stage,
        size_tier=job.size_tier,
        source_bytes=int(job.source_bytes or 0),
        source_chars=int(job.source_chars) if job.source_chars is not None else None,
        chapter_count=int(job.chapter_count) if job.chapter_count is not None else None,
        requested_language=job.requested_language,
        resolved_language=job.resolved_language,
        auto_index_plan=job.auto_index_plan,
        bootstrap_plan=job.bootstrap_plan,
        readiness_mode=job.readiness_mode,
        error=job.error,
        lease_owner=job.lease_owner,
        lease_expires_at=normalize_utc_naive(job.lease_expires_at),
        started_at=normalize_utc_naive(job.started_at),
        finished_at=normalize_utc_naive(job.finished_at),
        created_at=normalize_utc_naive(job.created_at),
        updated_at=normalize_utc_naive(job.updated_at),
    )


def inspect_novel_ingest_job(db: Session, *, novel_id: int) -> NovelIngestJobSnapshot | None:
    if not isinstance(novel_id, int) or novel_id <= 0:
        return None
    job = db.query(NovelIngestJob).filter(NovelIngestJob.novel_id == novel_id).first()
    if job is None:
        return None
    return serialize_novel_ingest_job(job)


def inspect_novel_ingest_jobs(
    db: Session,
    *,
    novel_ids: Iterable[int],
) -> dict[int, NovelIngestJobSnapshot]:
    normalized_novel_ids = sorted(
        {
            int(novel_id)
            for novel_id in novel_ids
            if isinstance(novel_id, int) and novel_id > 0
        }
    )
    if not normalized_novel_ids:
        return {}

    jobs = (
        db.query(NovelIngestJob)
        .filter(NovelIngestJob.novel_id.in_(normalized_novel_ids))
        .all()
    )
    return {int(job.novel_id): serialize_novel_ingest_job(job) for job in jobs}


def is_stale_running_novel_ingest_job(
    job: NovelIngestJob,
    *,
    settings: Settings | None = None,
    now=None,
) -> bool:
    resolved_settings = settings or get_settings()
    return is_stale_running_job(
        status=job.status,
        running_status=INGEST_JOB_STATUS_RUNNING,
        lease_expires_at=job.lease_expires_at,
        updated_at=job.updated_at,
        created_at=job.created_at,
        stale_timeout_seconds=int(resolved_settings.ingest_job_stale_timeout_seconds or 0),
        now=now,
    )


def _running_stale_filter(now, settings: Settings):
    return stale_running_job_filter(
        NovelIngestJob,
        now=now,
        stale_timeout_seconds=int(settings.ingest_job_stale_timeout_seconds or 0),
    )


def _requeue_as_accepted(job: NovelIngestJob) -> None:
    job.status = INGEST_JOB_STATUS_QUEUED
    job.stage = INGEST_JOB_STAGE_ACCEPTED
    job.error = None
    job.lease_owner = None
    job.lease_expires_at = None
    job.started_at = None
    job.finished_at = None


def enqueue_novel_ingest_job(
    db: Session,
    *,
    novel_id: int,
    source_bytes: int,
    requested_language: str | None,
) -> NovelIngestJob:
    job = db.query(NovelIngestJob).filter(NovelIngestJob.novel_id == novel_id).first()
    if job is None:
        job = NovelIngestJob(
            novel_id=novel_id,
            status=INGEST_JOB_STATUS_QUEUED,
            stage=INGEST_JOB_STAGE_ACCEPTED,
            source_bytes=max(int(source_bytes or 0), 0),
            requested_language=requested_language,
            error=None,
        )
        try:
            with db.begin_nested():
                db.add(job)
                db.flush()
            return job
        except IntegrityError:
            job = db.query(NovelIngestJob).filter(NovelIngestJob.novel_id == novel_id).first()
            if job is None:
                raise

    job.source_bytes = max(int(source_bytes or 0), int(job.source_bytes or 0), 0)
    job.requested_language = requested_language or job.requested_language
    _requeue_as_accepted(job)
    return job


def reset_novel_ingest_job_for_retry(db: Session, *, novel_id: int) -> NovelIngestJob | None:
    job = db.query(NovelIngestJob).filter(NovelIngestJob.novel_id == novel_id).first()
    if job is None:
        return None
    _requeue_as_accepted(job)
    return job


def claim_novel_ingest_job(
    *,
    novel_id: int,
    session_factory: Callable[[], Session],
    worker_id: str,
    settings: Settings,
) -> _NovelIngestClaim | None:
    db = session_factory()
    try:
        job = db.query(NovelIngestJob).filter(NovelIngestJob.novel_id == novel_id).first()
        if job is None:
            return None

        if job.status == INGEST_JOB_STATUS_COMPLETED:
            return None
        if job.status == INGEST_JOB_STATUS_RUNNING and not is_stale_running_novel_ingest_job(
            job,
            settings=settings,
        ):
            return None

        now = utcnow_naive()
        update_query = db.query(NovelIngestJob).filter(NovelIngestJob.id == job.id)
        if job.status == INGEST_JOB_STATUS_RUNNING:
            update_query = update_query.filter(
                NovelIngestJob.status == INGEST_JOB_STATUS_RUNNING,
                _running_stale_filter(now, settings),
            )
        else:
            update_query = update_query.filter(NovelIngestJob.status == job.status)

        claimed = update_query.update(
            claim_lease_values(
                NovelIngestJob,
                now=now,
                worker_id=worker_id,
                lease_seconds=int(settings.ingest_job_lease_seconds or 0),
                extra_updates={
                    NovelIngestJob.status: INGEST_JOB_STATUS_RUNNING,
                    NovelIngestJob.error: None,
                    NovelIngestJob.finished_at: None,
                },
            ),
            synchronize_session=False,
        )
        if claimed != 1:
            db.rollback()
            return None
        db.commit()
        return _NovelIngestClaim(job_id=int(job.id), novel_id=novel_id, worker_id=worker_id)
    finally:
        db.close()


def select_next_novel_ingest_job_novel_id(
    *,
    session_factory: Callable[[], Session],
    settings: Settings | None = None,
) -> int | None:
    resolved_settings = settings or get_settings()
    db = session_factory()
    try:
        now = utcnow_naive()
        query = db.query(NovelIngestJob.novel_id).filter(
            or_(
                NovelIngestJob.status == INGEST_JOB_STATUS_QUEUED,
                and_(
                    NovelIngestJob.status == INGEST_JOB_STATUS_RUNNING,
                    _running_stale_filter(now, resolved_settings),
                ),
            )
        )
        row = query.order_by(NovelIngestJob.created_at.asc(), NovelIngestJob.id.asc()).first()
        if row is None:
            return None
        return int(row[0])
    finally:
        db.close()
