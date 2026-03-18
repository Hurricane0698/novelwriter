# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Protocol

from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import DerivedAssetJob

logger = logging.getLogger(__name__)

DERIVED_ASSET_KIND_WINDOW_INDEX = "window_index"

DERIVED_ASSET_JOB_STATUS_QUEUED = "queued"
DERIVED_ASSET_JOB_STATUS_RUNNING = "running"
DERIVED_ASSET_JOB_STATUS_COMPLETED = "completed"
DERIVED_ASSET_JOB_STATUS_FAILED = "failed"
ACTIVE_DERIVED_ASSET_JOB_STATUSES = frozenset(
    {
        DERIVED_ASSET_JOB_STATUS_QUEUED,
        DERIVED_ASSET_JOB_STATUS_RUNNING,
    }
)


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).astimezone(timezone.utc).replace(tzinfo=None)


def _normalize_utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


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
        lease_expires_at=_normalize_utc_naive(job.lease_expires_at),
        started_at=_normalize_utc_naive(job.started_at),
        finished_at=_normalize_utc_naive(job.finished_at),
        created_at=_normalize_utc_naive(job.created_at),
        updated_at=_normalize_utc_naive(job.updated_at),
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


def is_active_derived_asset_job_status(status: str | None) -> bool:
    return status in ACTIVE_DERIVED_ASSET_JOB_STATUSES


def is_stale_running_derived_asset_job(
    job: DerivedAssetJob,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> bool:
    if job.status != DERIVED_ASSET_JOB_STATUS_RUNNING:
        return False

    current_time = _normalize_utc_naive(now) or _utcnow_naive()
    lease_expires_at = _normalize_utc_naive(job.lease_expires_at)
    if lease_expires_at is not None:
        return lease_expires_at <= current_time

    resolved_settings = settings or get_settings()
    stale_timeout = int(resolved_settings.derived_asset_job_stale_timeout_seconds or 0)
    if stale_timeout <= 0:
        return False

    updated_at = _normalize_utc_naive(job.updated_at) or _normalize_utc_naive(job.created_at)
    if updated_at is None:
        return False
    return updated_at <= (current_time - timedelta(seconds=stale_timeout))


def _running_stale_filter(now: datetime, settings: Settings):
    stale_timeout = int(settings.derived_asset_job_stale_timeout_seconds or 0)
    if stale_timeout > 0:
        stale_cutoff = now - timedelta(seconds=stale_timeout)
        return or_(
            and_(
                DerivedAssetJob.lease_expires_at.is_not(None),
                DerivedAssetJob.lease_expires_at <= now,
            ),
            and_(
                DerivedAssetJob.lease_expires_at.is_(None),
                DerivedAssetJob.updated_at <= stale_cutoff,
            ),
        )
    return and_(
        DerivedAssetJob.lease_expires_at.is_not(None),
        DerivedAssetJob.lease_expires_at <= now,
    )


def _resolve_lease_expiry(now: datetime, lease_seconds: int) -> datetime | None:
    if lease_seconds <= 0:
        return None
    return now + timedelta(seconds=lease_seconds)


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
        job.lease_owner = None
        job.lease_expires_at = None
        job.finished_at = None

    if (
        job.status == DERIVED_ASSET_JOB_STATUS_COMPLETED
        and int(job.completed_revision or 0) >= int(job.target_revision or 0)
    ):
        return job

    if job.status != DERIVED_ASSET_JOB_STATUS_RUNNING:
        job.status = DERIVED_ASSET_JOB_STATUS_QUEUED
        job.error = None
        job.result = {}
        job.lease_owner = None
        job.lease_expires_at = None
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

        now = _utcnow_naive()
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
            {
                DerivedAssetJob.status: DERIVED_ASSET_JOB_STATUS_RUNNING,
                DerivedAssetJob.claimed_revision: target_revision,
                DerivedAssetJob.error: None,
                DerivedAssetJob.lease_owner: worker_id,
                DerivedAssetJob.lease_expires_at: _resolve_lease_expiry(
                    now,
                    int(settings.derived_asset_job_lease_seconds or 0),
                ),
                DerivedAssetJob.started_at: now,
                DerivedAssetJob.finished_at: None,
                DerivedAssetJob.updated_at: now,
            },
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
        )
    finally:
        db.close()


def _finalize_success(
    *,
    claim: _DerivedAssetClaim,
    adapter: DerivedAssetJobAdapter,
    build_output: Any,
    session_factory: Callable[[], Session],
) -> bool:
    db = session_factory()
    try:
        job = db.query(DerivedAssetJob).filter(DerivedAssetJob.id == claim.job_id).first()
        if job is None:
            return False
        if (
            job.status != DERIVED_ASSET_JOB_STATUS_RUNNING
            or job.lease_owner != claim.worker_id
            or int(job.claimed_revision or 0) != claim.target_revision
        ):
            logger.warning(
                "Skipping derived-asset success persistence after lease loss",
                extra={
                    "job_id": claim.job_id,
                    "novel_id": claim.novel_id,
                    "asset_kind": claim.asset_kind,
                },
            )
            return False

        persisted = adapter.persist_success(
            db=db,
            job=job,
            target_revision=claim.target_revision,
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
        job.error = None
        job.lease_owner = None
        job.lease_expires_at = None

        if persisted.superseded or int(job.target_revision or 0) > claim.target_revision:
            job.status = DERIVED_ASSET_JOB_STATUS_QUEUED
            job.finished_at = None
            db.commit()
            return True

        job.status = DERIVED_ASSET_JOB_STATUS_COMPLETED
        job.finished_at = _utcnow_naive()
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
        job = db.query(DerivedAssetJob).filter(DerivedAssetJob.id == claim.job_id).first()
        if job is None:
            return False
        if (
            job.status != DERIVED_ASSET_JOB_STATUS_RUNNING
            or job.lease_owner != claim.worker_id
            or int(job.claimed_revision or 0) != claim.target_revision
        ):
            logger.warning(
                "Skipping derived-asset failure persistence after lease loss",
                extra={
                    "job_id": claim.job_id,
                    "novel_id": claim.novel_id,
                    "asset_kind": claim.asset_kind,
                },
            )
            return False

        superseded = adapter.persist_failure(
            db=db,
            job=job,
            target_revision=claim.target_revision,
            error=error,
        )
        job.result = {}
        job.lease_owner = None
        job.lease_expires_at = None

        if superseded or int(job.target_revision or 0) > claim.target_revision:
            job.status = DERIVED_ASSET_JOB_STATUS_QUEUED
            job.error = None
            job.finished_at = None
            db.commit()
            return True

        job.status = DERIVED_ASSET_JOB_STATUS_FAILED
        job.error = error
        job.finished_at = _utcnow_naive()
        db.commit()
        return False
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def run_derived_asset_job_until_idle(
    *,
    novel_id: int,
    adapter: DerivedAssetJobAdapter,
    session_factory: Callable[[], Session],
    settings: Settings | None = None,
) -> None:
    resolved_settings = settings or get_settings()
    worker_id = uuid.uuid4().hex

    while True:
        claim = _claim_derived_asset_job(
            novel_id=novel_id,
            asset_kind=adapter.asset_kind,
            session_factory=session_factory,
            worker_id=worker_id,
            settings=resolved_settings,
        )
        if claim is None:
            return

        try:
            build_output = adapter.build(
                novel_id=novel_id,
                target_revision=claim.target_revision,
                session_factory=session_factory,
                settings=resolved_settings,
            )
        except Exception as exc:
            logger.exception(
                "derived_asset[%s]: build failed for novel %s revision %s",
                adapter.asset_kind,
                novel_id,
                claim.target_revision,
            )
            if _finalize_failure(
                claim=claim,
                adapter=adapter,
                error=adapter.sanitize_error(exc),
                session_factory=session_factory,
            ):
                continue
            return

        if _finalize_success(
            claim=claim,
            adapter=adapter,
            build_output=build_output,
            session_factory=session_factory,
        ):
            continue
        return
