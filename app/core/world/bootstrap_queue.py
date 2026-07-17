from __future__ import annotations

import logging
from typing import Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.core.bootstrap_contract import (
    BOOTSTRAP_MODE_INITIAL,
    BOOTSTRAP_RESULT_QUEUED_SOURCE_INGEST_AUTO,
    build_bootstrap_trigger_result,
    is_running_status,
    is_stale_running_job,
)
from app.core.indexing.chapters import has_non_empty_chapter_text
from app.core.world.bootstrap_state import is_bootstrap_initialized
from app.models import BootstrapJob, Novel, NovelIngestJob

logger = logging.getLogger(__name__)

def _auto_bootstrap_llm_ready(settings: Settings) -> bool:
    if bool(getattr(settings, "ai_manual_disable", False)):
        return False

    deploy_mode = str(getattr(settings, "deploy_mode", "") or "").strip().lower()
    if deploy_mode == "hosted":
        base_url = getattr(settings, "hosted_llm_base_url", None) or getattr(settings, "openai_base_url", None)
        api_key = getattr(settings, "hosted_llm_api_key", None) or getattr(settings, "openai_api_key", None)
        model = getattr(settings, "hosted_llm_model", None) or getattr(settings, "openai_model", None)
    else:
        base_url = getattr(settings, "openai_base_url", None)
        api_key = getattr(settings, "openai_api_key", None)
        model = getattr(settings, "openai_model", None)

    return all(str(value or "").strip() for value in (base_url, api_key, model))


def ensure_ingest_bootstrap_job(
    novel_id: int,
    *,
    session_factory: Callable[[], Session],
    settings: Settings | None = None,
) -> BootstrapJob | None:
    resolved_settings = settings or get_settings()
    db = session_factory()
    try:
        novel = db.query(Novel).filter(Novel.id == novel_id).first()
        if novel is None:
            return None
        ingest_job = db.query(NovelIngestJob).filter(NovelIngestJob.novel_id == novel_id).first()
        if ingest_job is None or ingest_job.status != "completed":
            return None

        bootstrap_plan = (ingest_job.bootstrap_plan or "").strip()
        if bootstrap_plan == "manual_only":
            return None
        if not _auto_bootstrap_llm_ready(resolved_settings):
            logger.info(
                "bootstrap: skipping auto-bootstrap because LLM config is unavailable novel=%d plan=%s",
                novel_id,
                bootstrap_plan or "unknown",
            )
            return None
        if bootstrap_plan == "defer_until_index" and not is_window_index_ready(novel):
            return None
        if bootstrap_plan not in {"immediate", "defer_until_index"}:
            return None
        if not has_non_empty_chapter_text(db, novel_id):
            return None

        job = db.query(BootstrapJob).filter(BootstrapJob.novel_id == novel_id).first()
        if job and is_running_status(job.status):
            if is_stale_running_job(
                job,
                stale_after_seconds=resolved_settings.bootstrap_stale_job_timeout_seconds,
            ):
                logger.warning(
                    "Reclaiming stale auto bootstrap job",
                    extra={"novel_id": novel_id, "job_id": job.id, "status": job.status},
                )
            else:
                return None
        if is_bootstrap_initialized(job):
            return None

        if not job:
            job = BootstrapJob(novel_id=novel_id)
            db.add(job)

        job.mode = BOOTSTRAP_MODE_INITIAL
        job.draft_policy = None
        job.status = "pending"
        job.progress = {"step": 0, "detail": "queued"}
        job.result = build_bootstrap_trigger_result(
            mode=BOOTSTRAP_MODE_INITIAL,
            user_id=getattr(novel, "owner_id", None),
            queued_source=BOOTSTRAP_RESULT_QUEUED_SOURCE_INGEST_AUTO,
        )
        job.error = None

        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing_job = db.query(BootstrapJob).filter(BootstrapJob.novel_id == novel_id).first()
            if existing_job and (
                is_bootstrap_initialized(existing_job)
                or is_running_status(existing_job.status)
            ):
                return None
            raise

        db.refresh(job)
        logger.info(
            "bootstrap[%d]: auto-queued initial bootstrap novel=%d plan=%s",
            job.id,
            novel_id,
            bootstrap_plan,
        )
        return job
    finally:
        db.close()


def is_window_index_ready(novel: Novel) -> bool:
    current_revision = int(getattr(novel, "window_index_revision", 0) or 0)
    built_revision = int(getattr(novel, "window_index_built_revision", 0) or 0)
    return (
        current_revision > 0
        and built_revision >= current_revision
        and str(getattr(novel, "window_index_status", "") or "").strip().lower() == "fresh"
    )
