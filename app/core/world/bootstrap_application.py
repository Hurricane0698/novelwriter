# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Application orchestration for bootstrap trigger and status flows."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import Awaitable, Callable

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.core.bootstrap import (
    BOOTSTRAP_MODE_INDEX_REFRESH,
    BOOTSTRAP_MODE_INITIAL,
    BOOTSTRAP_MODE_REEXTRACT,
    BOOTSTRAP_RESULT_QUEUED_SOURCE_INGEST_AUTO,
    build_bootstrap_trigger_result,
    BootstrapRunSummary,
    bootstrap_job_queued_source,
    find_legacy_manual_draft_ambiguity,
    is_running_status,
    is_stale_running_job,
    RUNNING_BOOTSTRAP_STATUSES,
    resolve_bootstrap_trigger_user_id,
    resolve_reextract_draft_policy,
    run_bootstrap_job,
)
from app.core.events import record_event
from app.core.safety_fuses import ensure_ai_available
from app.core.world.crud import load_novel
from app.core.world.bootstrap_queue import is_window_index_ready
from app.core.indexing.chapters import has_non_empty_chapter_text
from app.core.world.bootstrap_state import is_bootstrap_initialized
from app.core.world.use_case_errors import WorldUseCaseError, detail_error_from_http_exception
from app.models import BootstrapJob, User
from app.schemas import BootstrapDraftPolicy, BootstrapTriggerRequest

logger = logging.getLogger(__name__)
_bootstrap_trigger_locks: dict[int, asyncio.Lock] = {}
_bootstrap_trigger_locks_guard = asyncio.Lock()
_LEGACY_REPAIR_SCRIPT = "scripts/fix_legacy_bootstrap_origin.py"
BOOTSTRAP_HOSTED_BYOK_DISABLED_CODE = "hosted_byok_disabled"
BOOTSTRAP_HOSTED_BYOK_DISABLED_MESSAGE = "Hosted beta uses platform-managed AI credentials only."


@dataclass(frozen=True, slots=True)
class BootstrapWorkerClaim:
    job_id: int
    novel_id: int
    user_id: int | None
    mode: str


def _matches_worker_source(job: BootstrapJob, *, queued_source_filter: str | None) -> bool:
    if queued_source_filter is None:
        return True
    return bootstrap_job_queued_source(job) == queued_source_filter


async def trigger_bootstrap(
    novel_id: int,
    *,
    body: BootstrapTriggerRequest | None,
    db: Session,
    current_user: User,
    llm_config: dict | None,
    settings: Settings | None = None,
    launch_bootstrap_job_fn: Callable[..., None] | None = None,
) -> BootstrapJob:
    resolved_settings = settings or get_settings()
    launcher = launch_bootstrap_job_fn or launch_bootstrap_job
    lock = await _get_bootstrap_trigger_lock(novel_id)

    async with lock:
        novel = load_novel(novel_id, db)
        if resolved_settings.deploy_mode == "hosted" and _uses_request_scoped_byok(llm_config):
            raise WorldUseCaseError(
                code=BOOTSTRAP_HOSTED_BYOK_DISABLED_CODE,
                message=BOOTSTRAP_HOSTED_BYOK_DISABLED_MESSAGE,
                status_code=400,
            )
        try:
            ensure_ai_available(
                db,
                billing_source=(
                    llm_config.get("billing_source_hint")
                    if isinstance(llm_config, dict)
                    else ("hosted" if resolved_settings.deploy_mode == "hosted" else None)
                ),
            )
        except HTTPException as exc:
            raise detail_error_from_http_exception(exc) from exc

        if not has_non_empty_chapter_text(db, novel_id):
            raise WorldUseCaseError(
                code="bootstrap_no_text",
                message="Novel has no non-empty chapter text to bootstrap",
                status_code=400,
            )

        job = db.query(BootstrapJob).filter(BootstrapJob.novel_id == novel_id).first()
        if job and is_running_status(job.status):
            if is_stale_running_job(
                job,
                stale_after_seconds=resolved_settings.bootstrap_stale_job_timeout_seconds,
            ):
                logger.warning(
                    "Reclaiming stale bootstrap job before retrigger",
                    extra={"novel_id": novel_id, "job_id": job.id, "status": job.status},
                )
            else:
                raise WorldUseCaseError(
                    code="bootstrap_already_running",
                    message="Bootstrap already running for this novel",
                    status_code=409,
                )

        bootstrap_initialized = is_bootstrap_initialized(job)
        mode, draft_policy = _resolve_trigger_params(body, bootstrap_initialized=bootstrap_initialized)

        if (
            mode == BOOTSTRAP_MODE_REEXTRACT
            and draft_policy == BootstrapDraftPolicy.REPLACE_BOOTSTRAP_DRAFTS
        ):
            legacy = find_legacy_manual_draft_ambiguity(db, novel_id=novel_id)
            if legacy.has_any():
                raise WorldUseCaseError(
                    code="bootstrap_legacy_ambiguity_conflict",
                    message=(
                        "Legacy ambiguity detected for reextract replacement: "
                        f"{len(legacy.entity_ids)} draft entities and {len(legacy.relationship_ids)} "
                        "draft relationships still use origin=manual from pre-origin-tracking data. "
                        f"Run `python3 {_LEGACY_REPAIR_SCRIPT} --novel-id {novel_id} --dry-run`, "
                        "review the output, then rerun with `--apply` before retrying."
                    ),
                    status_code=409,
                )

        if mode == BOOTSTRAP_MODE_INITIAL and bootstrap_initialized:
            raise WorldUseCaseError(
                code="bootstrap_initial_mode_not_allowed",
                message="initial mode is only allowed before bootstrap initialization",
                status_code=409,
            )
        if mode == BOOTSTRAP_MODE_INDEX_REFRESH and is_window_index_ready(novel):
            raise WorldUseCaseError(
                code="bootstrap_index_already_fresh",
                message="Whole-book retrieval is already fresh for this novel",
                status_code=409,
            )

        if not job:
            job = BootstrapJob(novel_id=novel_id)
            db.add(job)

        job.mode = mode
        job.draft_policy = draft_policy.value if draft_policy else None
        job.status = "pending"
        job.progress = {"step": 0, "detail": "queued"}
        job.result = {
            **build_bootstrap_trigger_result(mode=mode, user_id=current_user.id),
        }
        job.error = None

        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            existing_job = db.query(BootstrapJob).filter(BootstrapJob.novel_id == novel_id).first()
            if existing_job and is_running_status(existing_job.status):
                raise WorldUseCaseError(
                    code="bootstrap_already_running",
                    message="Bootstrap already running for this novel",
                    status_code=409,
                ) from exc
            raise WorldUseCaseError(
                code="bootstrap_trigger_conflict",
                message="Bootstrap trigger conflict, please retry",
                status_code=409,
            ) from exc

        db.refresh(job)

        if resolved_settings.deploy_mode == "hosted":
            logger.info(
                "bootstrap[%d]: queued for hosted worker novel=%d mode=%s",
                job.id,
                novel_id,
                mode,
            )
        else:
            launcher(
                db=db,
                job_id=job.id,
                user_id=current_user.id,
                llm_config=llm_config,
            )

        return job


def _uses_request_scoped_byok(llm_config: dict | None) -> bool:
    if not isinstance(llm_config, dict):
        return False
    return llm_config.get("billing_source_hint") == "byok"


def _claim_bootstrap_worker_job(
    *,
    session_factory: Callable[[], Session],
    settings: Settings,
    queued_source_filter: str | None,
) -> BootstrapWorkerClaim | None:
    db = session_factory()
    try:
        jobs = (
            db.query(BootstrapJob)
            .filter(BootstrapJob.status.in_(RUNNING_BOOTSTRAP_STATUSES))
            .order_by(BootstrapJob.updated_at.asc(), BootstrapJob.id.asc())
            .all()
        )
        for job in jobs:
            if not _matches_worker_source(job, queued_source_filter=queued_source_filter):
                continue
            if job.status == "pending":
                return BootstrapWorkerClaim(
                    job_id=job.id,
                    novel_id=job.novel_id,
                    user_id=resolve_bootstrap_trigger_user_id(job),
                    mode=job.mode,
                )
            if not is_running_status(job.status):
                continue
            if not is_stale_running_job(
                job,
                stale_after_seconds=settings.bootstrap_stale_job_timeout_seconds,
            ):
                continue
            logger.warning(
                "Reclaiming stale background bootstrap job",
                extra={"novel_id": job.novel_id, "job_id": job.id, "status": job.status},
            )
            job.status = "pending"
            job.progress = {"step": 0, "detail": "queued"}
            job.result = build_bootstrap_trigger_result(
                mode=job.mode,
                user_id=resolve_bootstrap_trigger_user_id(job),
                queued_source=bootstrap_job_queued_source(job),
            )
            job.error = None
            db.commit()
            return BootstrapWorkerClaim(
                job_id=job.id,
                novel_id=job.novel_id,
                user_id=resolve_bootstrap_trigger_user_id(job),
                mode=job.mode,
            )
        return None
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def run_next_bootstrap_job(
    *,
    session_factory: Callable[[], Session],
    settings: Settings | None = None,
    background_job_runner: Callable[..., Awaitable[None]] | None = None,
) -> bool:
    resolved_settings = settings or get_settings()
    queued_source_filter = (
        BOOTSTRAP_RESULT_QUEUED_SOURCE_INGEST_AUTO
        if resolved_settings.deploy_mode == "selfhost"
        else None
    )

    claim = _claim_bootstrap_worker_job(
        session_factory=session_factory,
        settings=resolved_settings,
        queued_source_filter=queued_source_filter,
    )
    if claim is None:
        return False

    logger.info(
        "bootstrap[%d]: background worker picked queued job novel=%d mode=%s source=%s",
        claim.job_id,
        claim.novel_id,
        claim.mode,
        queued_source_filter or "any",
    )
    runner = background_job_runner or run_bootstrap_background_job
    asyncio.run(
        runner(
            claim.job_id,
            session_factory=session_factory,
            user_id=claim.user_id,
            llm_config=None,
        )
    )
    return True


def get_bootstrap_status(
    novel_id: int,
    *,
    db: Session,
    settings: Settings | None = None,
) -> BootstrapJob:
    load_novel(novel_id, db)
    job = db.query(BootstrapJob).filter(BootstrapJob.novel_id == novel_id).first()
    if not job:
        raise WorldUseCaseError(
            code="bootstrap_job_not_found",
            message="Bootstrap job not found",
            status_code=404,
        )

    resolved_settings = settings or get_settings()
    if is_stale_running_job(job, stale_after_seconds=resolved_settings.bootstrap_stale_job_timeout_seconds):
        job.status = "failed"
        job.error = "Bootstrap job stale after restart; please retry."
        db.commit()
        db.refresh(job)
    return job


def launch_bootstrap_job(
    *,
    db: Session,
    job_id: int,
    user_id: int | None,
    llm_config: dict | None,
    task_scheduler: Callable[[Awaitable[None]], object] = asyncio.create_task,
    background_job_runner: Callable[..., Awaitable[None]] | None = None,
) -> None:
    background_session_factory = sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)
    runner = background_job_runner or run_bootstrap_background_job
    task_scheduler(
        runner(
            job_id,
            session_factory=background_session_factory,
            user_id=user_id,
            llm_config=llm_config,
        )
    )


async def run_bootstrap_background_job(
    job_id: int,
    *,
    session_factory: Callable[[], Session],
    user_id: int | None = None,
    llm_config: dict | None = None,
    bootstrap_runner: Callable[..., Awaitable[BootstrapRunSummary | None]] = run_bootstrap_job,
    record_event_fn: Callable[..., None] = record_event,
) -> None:
    summary = await bootstrap_runner(
        job_id,
        session_factory=session_factory,
        user_id=user_id,
        llm_config=llm_config,
    )
    if summary is None or user_id is None:
        return

    event_db = session_factory()
    try:
        record_event_fn(
            event_db,
            user_id,
            "bootstrap_run",
            novel_id=summary.novel_id,
            meta={
                "mode": summary.mode,
                "entities_found": summary.entities_found,
                "relationships_found": summary.relationships_found,
            },
        )
    finally:
        event_db.close()


async def _get_bootstrap_trigger_lock(novel_id: int) -> asyncio.Lock:
    async with _bootstrap_trigger_locks_guard:
        lock = _bootstrap_trigger_locks.get(novel_id)
        if lock is None:
            lock = asyncio.Lock()
            _bootstrap_trigger_locks[novel_id] = lock
        return lock


def _resolve_trigger_params(
    body: BootstrapTriggerRequest | None,
    *,
    bootstrap_initialized: bool,
) -> tuple[str, BootstrapDraftPolicy | None]:
    request = body or BootstrapTriggerRequest()
    mode_explicit = body is not None and "mode" in body.model_fields_set
    mode = request.mode.value
    if not mode_explicit:
        mode = BOOTSTRAP_MODE_INDEX_REFRESH if bootstrap_initialized else BOOTSTRAP_MODE_INITIAL

    if mode != BOOTSTRAP_MODE_REEXTRACT and request.draft_policy is not None:
        raise WorldUseCaseError(
            code="bootstrap_draft_policy_not_allowed",
            message="draft_policy is only supported for reextract mode",
            status_code=400,
        )

    if mode != BOOTSTRAP_MODE_REEXTRACT:
        return mode, None

    raw_policy = request.draft_policy.value if request.draft_policy else None
    policy = BootstrapDraftPolicy(resolve_reextract_draft_policy(raw_policy))
    if policy == BootstrapDraftPolicy.REPLACE_BOOTSTRAP_DRAFTS and not request.force:
        raise WorldUseCaseError(
            code="bootstrap_force_required",
            message="force=true is required for reextract with replace_bootstrap_drafts",
            status_code=400,
        )

    return mode, policy
