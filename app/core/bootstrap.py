# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import logging
import time
from typing import Callable

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.ai_client import AIClient
from app.core.bootstrap_contract import (
    BOOTSTRAP_DRAFT_POLICY_MERGE,
    BOOTSTRAP_DRAFT_POLICY_REPLACE_BOOTSTRAP_DRAFTS,
    BOOTSTRAP_MODE_INDEX_REFRESH,
    BOOTSTRAP_MODE_INITIAL,
    BOOTSTRAP_MODE_REEXTRACT,
    BOOTSTRAP_RESULT_QUEUED_SOURCE_INGEST_AUTO,
    BOOTSTRAP_RESULT_QUEUED_SOURCE_KEY,
    BOOTSTRAP_RESULT_QUEUED_USER_ID_KEY,
    BOOTSTRAP_STATUS_SEQUENCE,
    BootstrapRunSummary,
    DEFAULT_STALE_JOB_TIMEOUT_SECONDS,
    LegacyDraftAmbiguity,
    RUNNING_BOOTSTRAP_STATUSES,
    bootstrap_job_queued_source,
    build_bootstrap_trigger_result,
    is_running_status,
    is_stale_running_job,
    resolve_bootstrap_mode,
    resolve_bootstrap_trigger_user_id,
    resolve_reextract_draft_policy,
    transition_bootstrap_job,
)
from app.core.bootstrap_errors import (
    BOOTSTRAP_GENERIC_ERROR_KEY,
    BOOTSTRAP_GENERIC_ERROR_MESSAGE,
    BOOTSTRAP_PARSE_ERROR_KEY,
    BOOTSTRAP_PARSE_ERROR_MESSAGE,
    BOOTSTRAP_TIMEOUT_ERROR_KEY,
    BOOTSTRAP_TIMEOUT_ERROR_MESSAGE,
    sanitize_bootstrap_error,
)
from app.core.bootstrap_heartbeat import start_bootstrap_job_heartbeat
from app.core.bootstrap_persistence import (
    LEGACY_ORIGIN_TRACKING_CUTOFF,
    find_legacy_manual_draft_ambiguity,
    persist_bootstrap_output,
)
from app.core.bootstrap_refinement import (
    BootstrapRefinementResult,
    build_bootstrap_refinement_inputs,
    refine_candidates_with_llm,
)
from app.core.bootstrap_runtime import (
    BootstrapRuntimeDeps,
    begin_bootstrap_runtime,
    begin_refining,
    finalize_bootstrap_run,
    handle_bootstrap_failure,
    load_runtime_context,
    persist_pre_refine_index,
    prepare_bootstrap_artifacts,
    run_bootstrap_refinement,
)
from app.core.indexing.state_proto_executor import execute_state_proto_build
from app.core.indexing.state_proto_targets import load_state_proto_target_specs
from app.core.llm_semaphore import (
    acquire_background_llm_slot_blocking,
    release_background_llm_slot,
)
from app.core.llm_config import ResolvedLlmConfig
from app.database import SessionLocal

logger = logging.getLogger(__name__)


async def run_bootstrap_job(
    job_id: int,
    *,
    session_factory: Callable[[], Session] | None = None,
    client: AIClient | None = None,
    user_id: int | None = None,
    llm_config: ResolvedLlmConfig | None = None,
) -> BootstrapRunSummary | None:
    make_session = session_factory or SessionLocal
    db = make_session()
    deps = BootstrapRuntimeDeps(
        get_settings=get_settings,
        start_bootstrap_job_heartbeat=start_bootstrap_job_heartbeat,
        load_state_proto_target_specs=load_state_proto_target_specs,
        execute_state_proto_build=execute_state_proto_build,
        acquire_background_llm_slot_blocking=acquire_background_llm_slot_blocking,
        release_background_llm_slot=release_background_llm_slot,
        sanitize_bootstrap_error=sanitize_bootstrap_error,
    )
    index_persisted = False
    target_index_revision = 0
    job_novel_id: int | None = None
    heartbeat_state = None
    run_started_at = time.monotonic()
    try:
        context = load_runtime_context(
            db=db,
            job_id=job_id,
            user_id=user_id,
            deps=deps,
        )
        if context is None:
            return None

        job_novel_id = context.job.novel_id
        target_index_revision = context.target_index_revision
        heartbeat_state = begin_bootstrap_runtime(
            context,
            session_factory=make_session,
            deps=deps,
        )
        artifacts = prepare_bootstrap_artifacts(context, deps=deps)
        persist_pre_refine_index(context, artifacts)
        index_persisted = True
        begin_refining(context)
        refinement = await run_bootstrap_refinement(
            context,
            artifacts,
            deps=deps,
            client=client,
            llm_config=llm_config,
        )
        summary = finalize_bootstrap_run(context, refinement, deps=deps)
        logger.info(
            "bootstrap[%d]: completed mode=%s entities=%d relationships=%d duration_s=%.1f",
            job_id,
            summary.mode,
            summary.entities_found,
            summary.relationships_found,
            time.monotonic() - run_started_at,
        )
        return summary
    except Exception as exc:  # pragma: no cover - defensive background task guard
        handle_bootstrap_failure(
            db=db,
            job_id=job_id,
            job_novel_id=job_novel_id,
            target_index_revision=target_index_revision,
            index_persisted=index_persisted,
            deps=deps,
            exc=exc,
        )
        return None
    finally:
        if heartbeat_state is not None:
            stop_event, thread = heartbeat_state
            stop_event.set()
            thread.join(timeout=1.0)
        db.close()


__all__ = [
    "BOOTSTRAP_DRAFT_POLICY_MERGE",
    "BOOTSTRAP_DRAFT_POLICY_REPLACE_BOOTSTRAP_DRAFTS",
    "BOOTSTRAP_GENERIC_ERROR_KEY",
    "BOOTSTRAP_GENERIC_ERROR_MESSAGE",
    "BOOTSTRAP_MODE_INDEX_REFRESH",
    "BOOTSTRAP_MODE_INITIAL",
    "BOOTSTRAP_MODE_REEXTRACT",
    "BOOTSTRAP_RESULT_QUEUED_SOURCE_INGEST_AUTO",
    "BOOTSTRAP_RESULT_QUEUED_SOURCE_KEY",
    "BOOTSTRAP_PARSE_ERROR_KEY",
    "BOOTSTRAP_PARSE_ERROR_MESSAGE",
    "BOOTSTRAP_RESULT_QUEUED_USER_ID_KEY",
    "BOOTSTRAP_STATUS_SEQUENCE",
    "BOOTSTRAP_TIMEOUT_ERROR_KEY",
    "BOOTSTRAP_TIMEOUT_ERROR_MESSAGE",
    "BootstrapRefinementResult",
    "BootstrapRunSummary",
    "DEFAULT_STALE_JOB_TIMEOUT_SECONDS",
    "LEGACY_ORIGIN_TRACKING_CUTOFF",
    "LegacyDraftAmbiguity",
    "RUNNING_BOOTSTRAP_STATUSES",
    "bootstrap_job_queued_source",
    "build_bootstrap_refinement_inputs",
    "build_bootstrap_trigger_result",
    "find_legacy_manual_draft_ambiguity",
    "is_running_status",
    "is_stale_running_job",
    "persist_bootstrap_output",
    "refine_candidates_with_llm",
    "resolve_bootstrap_mode",
    "resolve_bootstrap_trigger_user_id",
    "resolve_reextract_draft_policy",
    "run_bootstrap_job",
    "transition_bootstrap_job",
]
