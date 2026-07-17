# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Iterable, Protocol

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.core.job_runtime import (
    apply_row_updates,
    claim_lease_values,
    refresh_lease_values,
    is_stale_running_job,
    normalize_utc_naive,
    release_lease_values,
    run_job_until_idle,
    stale_running_job_filter,
    utcnow_naive,
)
from app.models import DerivedAssetJob

logger = logging.getLogger(__name__)

DERIVED_ASSET_KIND_WINDOW_INDEX = "window_index"

DERIVED_ASSET_JOB_STATUS_QUEUED = "queued"
DERIVED_ASSET_JOB_STATUS_RUNNING = "running"
DERIVED_ASSET_JOB_STATUS_COMPLETED = "completed"
DERIVED_ASSET_JOB_STATUS_FAILED = "failed"


@dataclass(slots=True)
class DerivedAssetJobSnapshot:
    job_id: int
    novel_id: int
    asset_kind: str
    status: str
    target_revision: int
    claimed_revision: int | None
    completed_revision: int | None
    result: dict[str, Any]
    error: str | None
    lease_owner: str | None
    lease_expires_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(slots=True)
class DerivedAssetPersistResult:
    superseded: bool = False
    completed_revision: int | None = None
    next_target_revision: int | None = None
    result: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class _DerivedAssetClaim:
    job_id: int
    novel_id: int
    asset_kind: str
    target_revision: int
    worker_id: str
    started_at: datetime
    queue_wait_ms: float | None


class DerivedAssetJobAdapter(Protocol):
    asset_kind: str

    def build(
        self,
        *,
        novel_id: int,
        target_revision: int,
        session_factory: Callable[[], Session],
        settings: Settings,
    ) -> Any: ...

    def persist_success(
        self,
        *,
        db: Session,
        job: DerivedAssetJob,
        target_revision: int,
        claim: _DerivedAssetClaim,
        finished_at: datetime,
        build_output: Any,
    ) -> DerivedAssetPersistResult: ...

    def persist_failure(
        self,
        *,
        db: Session,
        job: DerivedAssetJob,
        target_revision: int,
        error: str,
    ) -> bool: ...

    def sanitize_error(self, exc: Exception) -> str: ...


def serialize_derived_asset_job(job: DerivedAssetJob) -> DerivedAssetJobSnapshot:
    return DerivedAssetJobSnapshot(
        job_id=job.id,
        novel_id=job.novel_id,
        asset_kind=job.asset_kind,
        status=job.status,
        target_revision=int(job.target_revision or 0),
        claimed_revision=int(job.claimed_revision) if job.claimed_revision is not None else None,
        completed_revision=int(job.completed_revision) if job.completed_revision is not None else None,
        result=dict(job.result or {}),
        error=job.error,
        lease_owner=job.lease_owner,
        lease_expires_at=normalize_utc_naive(job.lease_expires_at),
        started_at=normalize_utc_naive(job.started_at),
        finished_at=normalize_utc_naive(job.finished_at),
        created_at=normalize_utc_naive(job.created_at),
        updated_at=normalize_utc_naive(job.updated_at),
    )


def inspect_derived_asset_job(
    db: Session,
    *,
    novel_id: int,
    asset_kind: str,
) -> DerivedAssetJobSnapshot | None:
    job = (
        db.query(DerivedAssetJob)
        .filter(
            DerivedAssetJob.novel_id == novel_id,
            DerivedAssetJob.asset_kind == asset_kind,
        )
        .first()
    )
    if job is None:
        return None
    return serialize_derived_asset_job(job)


def inspect_derived_asset_jobs(
    db: Session,
    *,
    novel_ids: Iterable[int],
    asset_kind: str,
) -> dict[int, DerivedAssetJobSnapshot]:
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
        db.query(DerivedAssetJob)
        .filter(
            DerivedAssetJob.novel_id.in_(normalized_novel_ids),
            DerivedAssetJob.asset_kind == asset_kind,
        )
        .all()
    )
    return {
        int(job.novel_id): serialize_derived_asset_job(job)
        for job in jobs
    }


def is_stale_running_derived_asset_job(
    job: DerivedAssetJob,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> bool:
    resolved_settings = settings or get_settings()
    return is_stale_running_job(
        status=job.status,
        running_status=DERIVED_ASSET_JOB_STATUS_RUNNING,
        lease_expires_at=job.lease_expires_at,
        updated_at=job.updated_at,
        created_at=job.created_at,
        stale_timeout_seconds=int(resolved_settings.derived_asset_job_stale_timeout_seconds or 0),
        now=now,
    )


def _running_stale_filter(now: datetime, settings: Settings):
    return stale_running_job_filter(
        DerivedAssetJob,
        now=now,
        stale_timeout_seconds=int(settings.derived_asset_job_stale_timeout_seconds or 0),
    )


def enqueue_derived_asset_job(
    db: Session,
    *,
    novel_id: int,
    asset_kind: str,
    target_revision: int,
    settings: Settings | None = None,
) -> DerivedAssetJob:
    resolved_settings = settings or get_settings()
    normalized_target = max(int(target_revision or 0), 0)
    job = (
        db.query(DerivedAssetJob)
        .filter(
            DerivedAssetJob.novel_id == novel_id,
            DerivedAssetJob.asset_kind == asset_kind,
        )
        .first()
    )
    if job is None:
        job = DerivedAssetJob(
            novel_id=novel_id,
            asset_kind=asset_kind,
            status=DERIVED_ASSET_JOB_STATUS_QUEUED,
            target_revision=normalized_target,
            result={},
            error=None,
        )
        try:
            with db.begin_nested():
                db.add(job)
                db.flush()
            return job
        except IntegrityError:
            job = (
                db.query(DerivedAssetJob)
                .filter(
                    DerivedAssetJob.novel_id == novel_id,
                    DerivedAssetJob.asset_kind == asset_kind,
                )
                .first()
            )
            if job is None:
                raise

    job.target_revision = max(int(job.target_revision or 0), normalized_target)
    if is_stale_running_derived_asset_job(job, settings=resolved_settings):
        logger.warning(
            "Reclaiming stale derived-asset job before enqueue",
            extra={
                "job_id": job.id,
                "novel_id": novel_id,
                "asset_kind": asset_kind,
            },
        )
        job.status = DERIVED_ASSET_JOB_STATUS_QUEUED
        job.claimed_revision = None
        job.lease_owner = None
        job.lease_expires_at = None
        job.started_at = None
        job.finished_at = None

    if (
        job.status == DERIVED_ASSET_JOB_STATUS_COMPLETED
        and int(job.completed_revision or 0) >= int(job.target_revision or 0)
    ):
        return job

    preserve_last_completion = (
        job.status == DERIVED_ASSET_JOB_STATUS_COMPLETED
        and int(job.completed_revision or 0) > 0
    )

    if job.status != DERIVED_ASSET_JOB_STATUS_RUNNING:
        job.status = DERIVED_ASSET_JOB_STATUS_QUEUED
        job.error = None
        job.lease_owner = None
        job.lease_expires_at = None
        job.claimed_revision = None
        job.started_at = None
        if not preserve_last_completion:
            job.result = {}
            job.finished_at = None
    return job


def _claim_derived_asset_job(
    *,
    novel_id: int,
    asset_kind: str,
    session_factory: Callable[[], Session],
    worker_id: str,
    settings: Settings,
) -> _DerivedAssetClaim | None:
    db = session_factory()
    try:
        job = (
            db.query(DerivedAssetJob)
            .filter(
                DerivedAssetJob.novel_id == novel_id,
                DerivedAssetJob.asset_kind == asset_kind,
            )
            .first()
        )
        if job is None:
            return None

        target_revision = int(job.target_revision or 0)
        completed_revision = int(job.completed_revision or 0)
        if target_revision <= completed_revision and job.status == DERIVED_ASSET_JOB_STATUS_COMPLETED:
            return None

        if job.status == DERIVED_ASSET_JOB_STATUS_RUNNING and not is_stale_running_derived_asset_job(
            job,
            settings=settings,
        ):
            return None

        now = utcnow_naive()
        queue_wait_ms: float | None = None
        if job.status == DERIVED_ASSET_JOB_STATUS_QUEUED:
            queued_at = normalize_utc_naive(job.updated_at) or normalize_utc_naive(job.created_at)
            if queued_at is not None:
                queue_wait_ms = round(max((now - queued_at).total_seconds() * 1000, 0.0), 1)
        update_query = (
            db.query(DerivedAssetJob)
            .filter(
                DerivedAssetJob.id == job.id,
                func.coalesce(DerivedAssetJob.completed_revision, 0) < DerivedAssetJob.target_revision,
            )
        )
        if job.status == DERIVED_ASSET_JOB_STATUS_RUNNING:
            update_query = update_query.filter(
                DerivedAssetJob.status == DERIVED_ASSET_JOB_STATUS_RUNNING,
                _running_stale_filter(now, settings),
            )
        else:
            update_query = update_query.filter(DerivedAssetJob.status == job.status)

        claimed = update_query.update(
            claim_lease_values(
                DerivedAssetJob,
                now=now,
                worker_id=worker_id,
                lease_seconds=int(settings.derived_asset_job_lease_seconds or 0),
                extra_updates={
                    DerivedAssetJob.status: DERIVED_ASSET_JOB_STATUS_RUNNING,
                    DerivedAssetJob.claimed_revision: target_revision,
                    DerivedAssetJob.error: None,
                    DerivedAssetJob.finished_at: None,
                },
            ),
            synchronize_session=False,
        )
        if claimed != 1:
            db.rollback()
            return None

        db.commit()
        return _DerivedAssetClaim(
            job_id=job.id,
            novel_id=novel_id,
            asset_kind=asset_kind,
            target_revision=target_revision,
            worker_id=worker_id,
            started_at=now,
            queue_wait_ms=queue_wait_ms,
        )
    finally:
        db.close()


def _load_owned_running_job(
    db: Session,
    claim: _DerivedAssetClaim,
    *,
    action: str,
) -> DerivedAssetJob | None:
    """Load the claimed job; None when missing or the lease was lost."""
    job = db.query(DerivedAssetJob).filter(DerivedAssetJob.id == claim.job_id).first()
    if job is None:
        return None
    if (
        job.status != DERIVED_ASSET_JOB_STATUS_RUNNING
        or job.lease_owner != claim.worker_id
        or int(job.claimed_revision or 0) != claim.target_revision
    ):
        logger.warning(
            f"Skipping derived-asset {action} persistence after lease loss",
            extra={
                "job_id": claim.job_id,
                "novel_id": claim.novel_id,
                "asset_kind": claim.asset_kind,
            },
        )
        return None
    return job


def _requeue_for_newer_revision(db: Session, job: DerivedAssetJob) -> bool:
    apply_row_updates(
        job,
        release_lease_values(
            DerivedAssetJob,
            now=utcnow_naive(),
            extra_updates={
                DerivedAssetJob.status: DERIVED_ASSET_JOB_STATUS_QUEUED,
                DerivedAssetJob.claimed_revision: None,
                DerivedAssetJob.error: None,
                DerivedAssetJob.finished_at: None,
            },
        ),
    )
    db.commit()
    return True


def _finalize_success(
    *,
    claim: _DerivedAssetClaim,
    adapter: DerivedAssetJobAdapter,
    build_output: Any,
    session_factory: Callable[[], Session],
) -> bool:
    db = session_factory()
    try:
        job = _load_owned_running_job(db, claim, action="success")
        if job is None:
            return False

        finished_at = utcnow_naive()
        persisted = adapter.persist_success(
            db=db,
            job=job,
            target_revision=claim.target_revision,
            claim=claim,
            finished_at=finished_at,
            build_output=build_output,
        )
        if persisted.next_target_revision is not None:
            job.target_revision = max(
                int(job.target_revision or 0),
                int(persisted.next_target_revision),
            )
        if persisted.completed_revision is not None:
            job.completed_revision = max(
                int(job.completed_revision or 0),
                int(persisted.completed_revision),
            )
        job.result = dict(persisted.result or {})

        if persisted.superseded or int(job.target_revision or 0) > claim.target_revision:
            return _requeue_for_newer_revision(db, job)

        apply_row_updates(
            job,
            release_lease_values(
                DerivedAssetJob,
                now=finished_at,
                extra_updates={
                    DerivedAssetJob.status: DERIVED_ASSET_JOB_STATUS_COMPLETED,
                    DerivedAssetJob.claimed_revision: None,
                    DerivedAssetJob.error: None,
                    DerivedAssetJob.finished_at: finished_at,
                },
            ),
        )
        db.commit()
        return False
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _finalize_failure(
    *,
    claim: _DerivedAssetClaim,
    adapter: DerivedAssetJobAdapter,
    error: str,
    session_factory: Callable[[], Session],
) -> bool:
    db = session_factory()
    try:
        job = _load_owned_running_job(db, claim, action="failure")
        if job is None:
            return False

        superseded = adapter.persist_failure(
            db=db,
            job=job,
            target_revision=claim.target_revision,
            error=error,
        )
        job.result = {}

        if superseded or int(job.target_revision or 0) > claim.target_revision:
            return _requeue_for_newer_revision(db, job)

        finished_at = utcnow_naive()
        apply_row_updates(
            job,
            release_lease_values(
                DerivedAssetJob,
                now=finished_at,
                extra_updates={
                    DerivedAssetJob.status: DERIVED_ASSET_JOB_STATUS_FAILED,
                    DerivedAssetJob.claimed_revision: None,
                    DerivedAssetJob.error: error,
                    DerivedAssetJob.finished_at: finished_at,
                },
            ),
        )
        db.commit()
        return False
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _refresh_derived_asset_job_lease(
    *,
    claim: _DerivedAssetClaim,
    session_factory: Callable[[], Session],
    settings: Settings,
) -> bool:
    db = session_factory()
    try:
        job = db.query(DerivedAssetJob).filter(DerivedAssetJob.id == claim.job_id).first()
        if (
            job is None
            or job.status != DERIVED_ASSET_JOB_STATUS_RUNNING
            or job.lease_owner != claim.worker_id
            or int(job.claimed_revision or 0) != claim.target_revision
        ):
            return False

        apply_row_updates(
            job,
            refresh_lease_values(
                DerivedAssetJob,
                now=utcnow_naive(),
                lease_seconds=int(settings.derived_asset_job_lease_seconds or 0),
            ),
        )
        db.commit()
        return True
    except Exception:
        db.rollback()
        logger.warning(
            "Failed to refresh derived-asset lease heartbeat",
            extra={
                "job_id": claim.job_id,
                "novel_id": claim.novel_id,
                "asset_kind": claim.asset_kind,
            },
            exc_info=True,
        )
        return True
    finally:
        db.close()


class _DerivedAssetRuntimeAdapter:
    def __init__(
        self,
        *,
        adapter: DerivedAssetJobAdapter,
        session_factory: Callable[[], Session],
        settings: Settings,
    ) -> None:
        self._adapter = adapter
        self._session_factory = session_factory
        self._settings = settings

    def build(self, *, claim: _DerivedAssetClaim) -> Any:
        return self._adapter.build(
            novel_id=claim.novel_id,
            target_revision=claim.target_revision,
            session_factory=self._session_factory,
            settings=self._settings,
        )

    def finalize_success(self, *, claim: _DerivedAssetClaim, build_output: Any) -> bool:
        return _finalize_success(
            claim=claim,
            adapter=self._adapter,
            build_output=build_output,
            session_factory=self._session_factory,
        )

    def finalize_failure(self, *, claim: _DerivedAssetClaim, error: str) -> bool:
        return _finalize_failure(
            claim=claim,
            adapter=self._adapter,
            error=error,
            session_factory=self._session_factory,
        )

    def sanitize_error(self, exc: Exception) -> str:
        return self._adapter.sanitize_error(exc)

    def format_failure(self, claim: _DerivedAssetClaim) -> str:
        return (
            f"derived_asset[{claim.asset_kind}]: "
            f"build failed for novel {claim.novel_id} revision {claim.target_revision}"
        )

    def heartbeat(self, *, claim: _DerivedAssetClaim) -> bool:
        return _refresh_derived_asset_job_lease(
            claim=claim,
            session_factory=self._session_factory,
            settings=self._settings,
        )

    def heartbeat_interval_seconds(self, *, claim: _DerivedAssetClaim) -> float:
        lease_seconds = int(self._settings.derived_asset_job_lease_seconds or 0)
        if lease_seconds <= 0:
            return 0.0
        return max(min(lease_seconds / 3, 30.0), 1.0)


def run_derived_asset_job_until_idle(
    *,
    novel_id: int,
    adapter: DerivedAssetJobAdapter,
    session_factory: Callable[[], Session],
    settings: Settings | None = None,
) -> None:
    resolved_settings = settings or get_settings()
    run_job_until_idle(
        claim_next=lambda worker_id: _claim_derived_asset_job(
            novel_id=novel_id,
            asset_kind=adapter.asset_kind,
            session_factory=session_factory,
            worker_id=worker_id,
            settings=resolved_settings,
        ),
        adapter=_DerivedAssetRuntimeAdapter(
            adapter=adapter,
            session_factory=session_factory,
            settings=resolved_settings,
        ),
        logger=logger,
    )
