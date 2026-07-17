# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Public service boundary for copilot session/run orchestration."""

from __future__ import annotations

from sqlalchemy.orm import Session
from app.core.llm_config import ResolvedLlmConfig

from . import runtime_adapters as runtime_adapters_mod
from . import runtime_lookup as runtime_lookup_mod
from . import runtime_scenario as runtime_scenario_mod
from . import scope as scope_mod
from . import session_runtime as session_runtime_mod
from . import suggestions as suggestions_mod
from .execution_runtime import (
    ExecutionHooks,
    execute_copilot_run as execute_copilot_run_impl,
)
from .lifecycle_runtime import (
    RunLifecycleHooks,
    SessionLifecycleHooks,
    create_run as create_run_impl,
    open_or_reuse_session as open_or_reuse_session_impl,
)
from .runtime_errors import CopilotError, RunLeaseLostError
from app.models import CopilotRun, CopilotSession

MAX_ACTIVE_RUNS_PER_USER = 3


def open_or_reuse_session(
    db: Session,
    novel_id: int,
    user_id: int,
    mode: str,
    scope: str,
    context: dict | None,
    interaction_locale: str,
    display_title: str,
) -> tuple[CopilotSession, bool]:
    hooks = SessionLifecycleHooks(
        load_session_by_signature=runtime_lookup_mod.load_session_by_signature,
        is_session_signature_conflict=runtime_lookup_mod.is_session_signature_conflict,
        copilot_error_factory=lambda code, message, status_code: CopilotError(
            code=code,
            message=message,
            status_code=status_code,
        ),
    )
    return open_or_reuse_session_impl(
        hooks=hooks,
        db=db,
        novel_id=novel_id,
        user_id=user_id,
        mode=mode,
        scope=scope,
        context=context,
        interaction_locale=interaction_locale,
        display_title=display_title,
    )


def create_run(
    db: Session,
    session: CopilotSession,
    user_id: int,
    prompt: str,
    *,
    quick_action_id: str | None = None,
    resume_run_id: str | None = None,
    quota_reservation_id: int | None = None,
) -> CopilotRun:
    hooks = RunLifecycleHooks(
        count_active_runs=runtime_lookup_mod.count_active_runs,
        count_active_runs_in_session=runtime_lookup_mod.count_active_runs_in_session,
        is_active_session_run_conflict=runtime_lookup_mod.is_active_session_run_conflict,
        copilot_error_factory=lambda code, message, status_code: CopilotError(
            code=code,
            message=message,
            status_code=status_code,
        ),
    )
    return create_run_impl(
        hooks=hooks,
        db=db,
        session=session,
        user_id=user_id,
        prompt=prompt,
        quick_action_id=quick_action_id,
        resume_run_id=resume_run_id,
        quota_reservation_id=quota_reservation_id,
    )


async def execute_copilot_run(
    run_id: str,
    novel_id: int,
    user_id: int,
    llm_config: ResolvedLlmConfig,
) -> None:
    hooks = ExecutionHooks(
        derive_scenario=runtime_scenario_mod.derive_scenario,
        load_scope_snapshot=scope_mod.load_scope_snapshot,
        gather_evidence=scope_mod.gather_evidence,
        build_follow_up_conversation_messages=session_runtime_mod.build_follow_up_conversation_messages,
        compile_suggestions=suggestions_mod.compile_suggestions,
        run_tool_loop=runtime_adapters_mod.run_tool_loop,
        run_one_shot=runtime_adapters_mod.run_one_shot,
        lease_lost_error_type=RunLeaseLostError,
    )
    await execute_copilot_run_impl(
        hooks=hooks,
        run_id=run_id,
        novel_id=novel_id,
        user_id=user_id,
        llm_config=llm_config,
    )
