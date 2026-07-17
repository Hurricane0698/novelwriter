# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from sqlalchemy.orm import Session

from app.config import Settings
from app.core.ai_client import AIClient
from app.core.bootstrap_contract import (
    BOOTSTRAP_MODE_INDEX_REFRESH,
    BOOTSTRAP_MODE_INITIAL,
    BOOTSTRAP_MODE_REEXTRACT,
    BootstrapRunSummary,
    resolve_bootstrap_mode,
    resolve_bootstrap_trigger_user_id,
    resolve_reextract_draft_policy,
    transition_bootstrap_job,
)
from app.core.bootstrap_persistence import persist_bootstrap_output
from app.core.bootstrap_refinement import (
    BootstrapRefinementResult,
    build_bootstrap_refinement_inputs,
    refine_candidates_with_llm,
    sanitize_bootstrap_refinement_result,
)
from app.core.indexing.chapters import load_chapter_texts
from app.core.indexing.lifecycle import (
    mark_window_index_build_failed,
    mark_window_index_build_succeeded,
    resolve_window_index_target_revision,
)
from app.models import BootstrapJob, Novel

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BootstrapRuntimeDeps:
    get_settings: Callable[[], Settings]
    start_bootstrap_job_heartbeat: Callable[..., tuple[Any, Any] | None]
    load_state_proto_target_specs: Callable[[Session, int], list[Any]]
    execute_state_proto_build: Callable[..., Any]
    acquire_background_llm_slot_blocking: Callable[[], Awaitable[float | int | None]]
    release_background_llm_slot: Callable[[], None]
    sanitize_bootstrap_error: Callable[[Exception], tuple[str, str]]


@dataclass(slots=True)
class BootstrapRuntimeContext:
    db: Session
    job: BootstrapJob
    novel: Novel
    mode: str
    draft_policy: str | None
    settings: Settings
    resolved_user_id: int | None
    chapters: list[Any]
    target_index_revision: int


@dataclass(slots=True)
class BootstrapArtifacts:
    state_proto_output: Any
    importance: dict[str, int]
    cooccurrence_pairs: list[Any]
    allowed_alias_candidates: frozenset[str]
    supported_alias_candidates: frozenset[str]

    @property
    def pre_refine_index_payload(self) -> bytes:
        return self.state_proto_output.index_payload or b""


def _execute_state_proto_build(
    *,
    deps: BootstrapRuntimeDeps,
    context: BootstrapRuntimeContext,
    target_specs: list[Any],
):
    # Rust-canonical contract: when the Rust executor is unavailable the build
    # raises and the job fails loudly. No Python compat payload may be persisted.
    return deps.execute_state_proto_build(
        chapters=context.chapters,
        novel_language=getattr(context.novel, "language", None),
        target_specs=target_specs,
        existing_payload=getattr(context.novel, "window_index", None),
        settings=context.settings,
    )


def load_runtime_context(
    *,
    db: Session,
    job_id: int,
    user_id: int | None,
    deps: BootstrapRuntimeDeps,
) -> BootstrapRuntimeContext | None:
    job = db.query(BootstrapJob).filter(BootstrapJob.id == job_id).first()
    if job is None:
        return None

    novel = db.query(Novel).filter(Novel.id == job.novel_id).first()
    if novel is None:
        raise ValueError(f"Novel not found: {job.novel_id}")

    mode = resolve_bootstrap_mode(job.mode)
    draft_policy = (
        resolve_reextract_draft_policy(job.draft_policy)
        if mode == BOOTSTRAP_MODE_REEXTRACT
        else None
    )
    job.mode = mode
    job.draft_policy = draft_policy

    settings = deps.get_settings()
    resolved_user_id = user_id if user_id is not None else resolve_bootstrap_trigger_user_id(job)
    chapters = load_chapter_texts(db, job.novel_id)
    if not chapters:
        raise ValueError("Novel has no non-empty chapter text to bootstrap")

    target_index_revision = resolve_window_index_target_revision(
        novel,
        has_source_text=True,
    )
    return BootstrapRuntimeContext(
        db=db,
        job=job,
        novel=novel,
        mode=mode,
        draft_policy=draft_policy,
        settings=settings,
        resolved_user_id=resolved_user_id,
        chapters=chapters,
        target_index_revision=target_index_revision,
    )


def begin_bootstrap_runtime(
    context: BootstrapRuntimeContext,
    *,
    session_factory: Callable[[], Session],
    deps: BootstrapRuntimeDeps,
) -> tuple[Any, Any] | None:
    chapter_char_count = sum(len(chapter.text or "") for chapter in context.chapters)
    logger.info(
        "bootstrap[%d]: loaded %d chapters, %d chars",
        context.job.id,
        len(context.chapters),
        chapter_char_count,
    )
    transition_bootstrap_job(context.job, "tokenizing", detail="tokenizing chapters")
    context.db.commit()
    return deps.start_bootstrap_job_heartbeat(
        job_id=context.job.id,
        session_factory=session_factory,
        stale_timeout_seconds=int(context.settings.bootstrap_stale_job_timeout_seconds or 0),
    )


def prepare_bootstrap_artifacts(
    context: BootstrapRuntimeContext,
    *,
    deps: BootstrapRuntimeDeps,
) -> BootstrapArtifacts:
    target_specs = deps.load_state_proto_target_specs(context.db, context.novel.id)
    state_proto_output = _execute_state_proto_build(
        deps=deps,
        context=context,
        target_specs=target_specs,
    )
    refinement_inputs = build_bootstrap_refinement_inputs(
        index_payload=state_proto_output.index_payload,
        chapters=context.chapters,
        novel_language=getattr(context.novel, "language", None),
        common_words_dir=context.settings.bootstrap_common_words_dir,
        limit=context.settings.bootstrap_max_candidates,
        include_text_fallback=context.mode != BOOTSTRAP_MODE_INDEX_REFRESH,
    )
    if (
        refinement_inputs.supplemental_candidate_count
        or refinement_inputs.supplemental_pair_count
    ):
        logger.info(
            "bootstrap[%d]: supplemented refinement summary with %d text candidates and %d pairs",
            context.job.id,
            refinement_inputs.supplemental_candidate_count,
            refinement_inputs.supplemental_pair_count,
        )
    logger.info(
        "bootstrap[%d]: prepared state-proto artifacts → targets=%d segments=%d claims=%d mentions=%d",
        context.job.id,
        int(getattr(state_proto_output, "target_count", 0) or 0),
        int(getattr(state_proto_output, "segment_count", 0) or 0),
        int(getattr(state_proto_output, "claim_atom_count", 0) or 0),
        int(getattr(state_proto_output, "mention_posting_count", 0) or 0),
    )
    logger.info(
        "bootstrap[%d]: prepared refinement summary → %d candidates, %d pairs (%s)",
        context.job.id,
        len(refinement_inputs.importance),
        len(refinement_inputs.cooccurrence_pairs),
        context.mode,
    )
    return BootstrapArtifacts(
        state_proto_output=state_proto_output,
        importance=refinement_inputs.importance,
        cooccurrence_pairs=refinement_inputs.cooccurrence_pairs,
        allowed_alias_candidates=refinement_inputs.allowed_alias_candidates,
        supported_alias_candidates=refinement_inputs.supported_alias_candidates,
    )


def persist_pre_refine_index(
    context: BootstrapRuntimeContext,
    artifacts: BootstrapArtifacts,
) -> None:
    transition_bootstrap_job(
        context.job,
        "extracting",
        detail=(
            "extracting bootstrap targets"
            if context.mode != BOOTSTRAP_MODE_INDEX_REFRESH
            else "refreshing state index"
        ),
    )
    context.db.commit()

    transition_bootstrap_job(context.job, "windowing", detail="building window index")
    context.db.commit()

    mark_window_index_build_succeeded(
        context.novel,
        index_payload=artifacts.pre_refine_index_payload,
        revision=context.target_index_revision,
    )
    context.db.commit()


def begin_refining(context: BootstrapRuntimeContext) -> None:
    detail = (
        "refreshing window index only"
        if context.mode == BOOTSTRAP_MODE_INDEX_REFRESH
        else "refining entities and relationships"
    )
    transition_bootstrap_job(context.job, "refining", detail=detail)
    context.db.commit()


async def run_bootstrap_refinement(
    context: BootstrapRuntimeContext,
    artifacts: BootstrapArtifacts,
    *,
    deps: BootstrapRuntimeDeps,
    client: AIClient | None,
    llm_config: dict | None,
) -> BootstrapRefinementResult:
    if context.mode == BOOTSTRAP_MODE_INDEX_REFRESH:
        return BootstrapRefinementResult()

    llm_blocking_wait_seconds = float(await deps.acquire_background_llm_slot_blocking() or 0.0)
    current_result = dict(context.job.result or {})
    current_result["llm_blocking_wait_seconds"] = max(llm_blocking_wait_seconds, 0.0)
    current_result["llm_blocking_wait_count"] = int(current_result.get("llm_blocking_wait_count", 0) or 0) + 1
    context.job.result = current_result
    context.job.progress = {
        **(context.job.progress or {}),
        "llm_blocking_wait_seconds": current_result["llm_blocking_wait_seconds"],
        "llm_blocking_wait_count": current_result["llm_blocking_wait_count"],
    }
    context.db.commit()
    logger.info(
        "bootstrap[%d]: acquired LLM slot after %.3fs wait",
        context.job.id,
        current_result["llm_blocking_wait_seconds"],
    )
    try:
        refinement_coro = refine_candidates_with_llm(
            artifacts.importance,
            artifacts.cooccurrence_pairs,
            max_candidates=context.settings.bootstrap_max_candidates,
            temperature=context.settings.bootstrap_llm_temperature,
            client=client,
            llm_config=llm_config,
            user_id=context.resolved_user_id,
            novel_language=getattr(context.novel, "language", None),
        )
        timeout_seconds = float(getattr(context.settings, "bootstrap_llm_timeout_seconds", 0) or 0)
        if timeout_seconds > 0:
            refinement = await asyncio.wait_for(refinement_coro, timeout=timeout_seconds)
        else:
            refinement = await refinement_coro
        return sanitize_bootstrap_refinement_result(
            refinement,
            allowed_candidates=artifacts.allowed_alias_candidates,
            supported_alias_candidates=artifacts.supported_alias_candidates,
            novel_language=getattr(context.novel, "language", None),
        )
    finally:
        deps.release_background_llm_slot()


def finalize_bootstrap_run(
    context: BootstrapRuntimeContext,
    refinement: BootstrapRefinementResult,
    *,
    deps: BootstrapRuntimeDeps,
) -> BootstrapRunSummary:
    entities_found, relationships_found = persist_bootstrap_output(
        context.db,
        novel_id=context.job.novel_id,
        refinement=refinement,
        mode=context.mode,
        draft_policy=context.draft_policy,
    )
    target_specs = deps.load_state_proto_target_specs(context.db, context.novel.id)
    if target_specs:
        state_proto_output = _execute_state_proto_build(
            deps=deps,
            context=context,
            target_specs=list(target_specs),
        )
        mark_window_index_build_succeeded(
            context.novel,
            index_payload=state_proto_output.index_payload or b"",
            revision=context.target_index_revision,
        )
        context.db.commit()

    if context.mode in {BOOTSTRAP_MODE_INITIAL, BOOTSTRAP_MODE_REEXTRACT}:
        context.job.initialized = True

    transition_bootstrap_job(
        context.job,
        "completed",
        detail="bootstrap completed",
        result={
            "entities_found": entities_found,
            "relationships_found": relationships_found,
            "index_refresh_only": context.mode == BOOTSTRAP_MODE_INDEX_REFRESH,
        },
    )
    context.db.commit()
    return BootstrapRunSummary(
        novel_id=context.job.novel_id,
        mode=context.mode,
        entities_found=entities_found,
        relationships_found=relationships_found,
    )


def handle_bootstrap_failure(
    *,
    db: Session,
    job_id: int,
    job_novel_id: int | None,
    target_index_revision: int,
    index_persisted: bool,
    deps: BootstrapRuntimeDeps,
    exc: Exception,
) -> None:
    db.rollback()
    logger.exception("bootstrap background task failed")
    user_error, error_key = deps.sanitize_bootstrap_error(exc)
    try:
        failed_novel = db.query(Novel).filter(Novel.id == job_novel_id).first()
        if failed_novel is not None and not index_persisted:
            current_revision = int(getattr(failed_novel, "window_index_revision", 0) or 0)
            if current_revision <= target_index_revision:
                mark_window_index_build_failed(
                    failed_novel,
                    error=user_error,
                    revision=max(target_index_revision, current_revision, 1),
                )
        failed_job = db.query(BootstrapJob).filter(BootstrapJob.id == job_id).first()
        if failed_job and failed_job.status != "failed":
            transition_bootstrap_job(
                failed_job,
                "failed",
                detail="bootstrap failed",
                error=user_error,
            )
            failed_job.result = {
                **dict(failed_job.result or {}),
                "message_key": error_key,
            }
            db.commit()
    except Exception:
        db.rollback()


__all__ = [
    "BootstrapArtifacts",
    "BootstrapRuntimeContext",
    "BootstrapRuntimeDeps",
    "begin_bootstrap_runtime",
    "begin_refining",
    "finalize_bootstrap_run",
    "handle_bootstrap_failure",
    "load_runtime_context",
    "persist_pre_refine_index",
    "prepare_bootstrap_artifacts",
    "run_bootstrap_refinement",
]
