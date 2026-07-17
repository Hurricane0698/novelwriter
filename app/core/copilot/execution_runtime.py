# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Copilot run execution helpers.

Keeps the heavyweight async execution orchestration out of
``app.core.copilot.__init__`` while preserving root-module compatibility
wrappers for tests and callers that monkeypatch facade symbols.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from sqlalchemy.orm import Session

from app.core.ai_client import ToolCallUnsupportedError
from app.core.copilot.prompt_contract import PromptBuild
from app.core.copilot.prompting import (
    apply_quick_action_prompt,
    build_copilot_system_prompt_build,
    classify_turn_intent,
    should_preload_world_context,
)
from app.core.copilot.run_state import (
    call_copilot_llm,
    claim_run_for_execution,
    copilot_run_failed_message,
    ensure_run_lease,
    fail_run,
    parse_llm_response,
    resolve_run_interaction_locale,
)
from app.core.copilot.run_store import (
    persist_completed_run,
    persist_preloaded_evidence,
)
from app.core.copilot.scope import EvidenceItem, ScopeSnapshot
from app.core.copilot.session_runtime import canonicalize_session_context
from app.core.copilot.workspace import (
    Workspace,
    build_follow_up_workspace_seed,
)
from app.models import CopilotRun, Novel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OneShotDeps:
    acquire_llm_slot: Callable[[], Awaitable[Any]]
    release_llm_slot: Callable[[], None]
    renew_run_lease: Callable[..., bool]
    call_copilot_llm: Callable[
        [str, str, dict[str, Any] | None, int], Awaitable[str]
    ] = call_copilot_llm
    parse_llm_response: Callable[[str], dict[str, Any]] = parse_llm_response
    build_system_prompt: Callable[
        [ScopeSnapshot, list[EvidenceItem], str, str, dict[str, Any], str], PromptBuild
    ] = build_copilot_system_prompt_build
    lease_lost_error_factory: Callable[[str], Exception] = RuntimeError


@dataclass(frozen=True)
class ExecutionHooks:
    derive_scenario: Callable[[str, str, dict[str, Any] | None], str]
    load_scope_snapshot: Callable[
        [Session, Novel, str, str, dict[str, Any] | None], ScopeSnapshot
    ]
    gather_evidence: Callable[..., list[EvidenceItem]]
    build_follow_up_conversation_messages: Callable[
        [list[CopilotRun]], list[dict[str, str]]
    ]
    compile_suggestions: Callable[..., list[dict[str, Any]]]
    run_tool_loop: Callable[
        ...,
        Awaitable[tuple[dict[str, Any], list[EvidenceItem], Workspace | None]],
    ]
    run_one_shot: Callable[
        ...,
        Awaitable[tuple[dict[str, Any], list[EvidenceItem]]],
    ]
    lease_lost_error_type: type[BaseException]


def _build_follow_up_inputs(
    db: Session,
    *,
    build_follow_up_conversation_messages: Callable[
        [list[CopilotRun]], list[dict[str, str]]
    ],
    run: CopilotRun,
    inherited_workspace: dict[str, Any] | None,
) -> tuple[list[dict[str, str]], dict[str, Any] | None]:
    if inherited_workspace is not None:
        return [], None

    prior_completed_runs = (
        db.query(CopilotRun)
        .filter(
            CopilotRun.copilot_session_id == run.copilot_session_id,
            CopilotRun.id != run.id,
            CopilotRun.status == "completed",
        )
        .order_by(CopilotRun.created_at.asc(), CopilotRun.id.asc())
        .all()
    )
    if not prior_completed_runs:
        return [], None

    return (
        build_follow_up_conversation_messages(prior_completed_runs),
        build_follow_up_workspace_seed(prior_completed_runs[-1].workspace_json),
    )


async def run_one_shot(
    *,
    deps: OneShotDeps,
    snapshot: ScopeSnapshot,
    evidence: list[EvidenceItem],
    scenario: str,
    session_data: dict[str, Any],
    turn_intent: str,
    prompt: str,
    llm_config: dict[str, Any] | None,
    user_id: int,
    run_id: str = "",
    worker_id: str = "",
    db_factory: Callable[[], Session] | None = None,
) -> tuple[dict[str, Any], list[EvidenceItem]]:
    """Single LLM call with all evidence pre-loaded in the prompt."""
    prompt_build = deps.build_system_prompt(
        snapshot,
        evidence,
        scenario,
        session_data["interaction_locale"],
        session_data,
        turn_intent,
    )

    ensure_run_lease(deps, db_factory, run_id=run_id, worker_id=worker_id)

    await deps.acquire_llm_slot()
    try:
        response_text = await deps.call_copilot_llm(
            prompt_build.prompt_text, prompt, llm_config, user_id
        )
    finally:
        deps.release_llm_slot()

    ensure_run_lease(deps, db_factory, run_id=run_id, worker_id=worker_id)

    return deps.parse_llm_response(response_text), evidence


async def _run_with_degradation(
    hooks: ExecutionHooks,
    *,
    snapshot: ScopeSnapshot,
    evidence: list[EvidenceItem],
    scenario: str,
    session_data: dict[str, Any],
    turn_intent: str,
    prompt: str,
    llm_config: dict[str, Any] | None,
    user_id: int,
    run_id: str,
    worker_id: str,
    db_factory: Callable[[], Session],
    inherited_workspace: dict[str, Any] | None,
    prior_messages: list[dict[str, str]],
    workspace_seed: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[EvidenceItem], Workspace | None, str, str | None]:
    execution_mode = "tool_loop"
    degraded_reason: str | None = None

    try:
        parsed, final_evidence, workspace = await hooks.run_tool_loop(
            db_factory,
            session_data["novel_id"],
            session_data,
            prompt,
            llm_config,
            user_id,
            snapshot,
            scenario,
            evidence,
            turn_intent,
            run_id=run_id,
            worker_id=worker_id,
            inherited_workspace=inherited_workspace,
            prior_messages=prior_messages,
            workspace_seed=workspace_seed,
        )
        return parsed, final_evidence, workspace, execution_mode, degraded_reason
    except ToolCallUnsupportedError:
        logger.warning("Tool calls unsupported, degrading to one-shot", exc_info=True)
        execution_mode = "one_shot_unsupported"
        degraded_reason = "tools_not_supported"
    except hooks.lease_lost_error_type:
        logger.info("Copilot run %s lost lease during tool execution", run_id)
        raise
    except Exception as tool_loop_exc:
        logger.warning(
            "Tool loop failed (%s), attempting one-shot fallback",
            type(tool_loop_exc).__name__,
            exc_info=True,
        )
        execution_mode = "one_shot_fallback"
        degraded_reason = type(tool_loop_exc).__name__
        try:
            parsed, final_evidence = await hooks.run_one_shot(
                snapshot,
                evidence,
                scenario,
                session_data,
                turn_intent,
                prompt,
                llm_config,
                user_id,
                run_id=run_id,
                worker_id=worker_id,
                db_factory=db_factory,
            )
            return parsed, final_evidence, None, execution_mode, degraded_reason
        except hooks.lease_lost_error_type:
            logger.info("Copilot run %s lost lease during fallback execution", run_id)
            raise
        except Exception:
            raise tool_loop_exc from None

    parsed, final_evidence = await hooks.run_one_shot(
        snapshot,
        evidence,
        scenario,
        session_data,
        turn_intent,
        prompt,
        llm_config,
        user_id,
        run_id=run_id,
        worker_id=worker_id,
        db_factory=db_factory,
    )
    return parsed, final_evidence, None, execution_mode, degraded_reason


async def execute_copilot_run(
    *,
    hooks: ExecutionHooks,
    run_id: str,
    novel_id: int,
    user_id: int,
    llm_config: dict[str, Any] | None,
) -> None:
    """Execute one copilot run while keeping the root module as facade."""
    from app.database import SessionLocal

    worker_id = uuid.uuid4().hex
    db = SessionLocal()
    try:
        run = claim_run_for_execution(db, run_id=run_id, worker_id=worker_id)
        if not run:
            logger.info("Copilot run %s was not claimable for execution", run_id)
            return

        session = run.session
        if not session:
            fail_run(
                db, run, "session_not_found", "Session not found", worker_id=worker_id
            )
            return

        novel = db.get(Novel, novel_id)
        if not novel:
            fail_run(
                db, run, "novel_not_found", "Novel not found", worker_id=worker_id
            )
            return

        run_context = canonicalize_session_context(
            run.context_json
        ) or canonicalize_session_context(session.context_json)
        snapshot = hooks.load_scope_snapshot(
            db, novel, session.mode, session.scope, run_context
        )
        scenario = hooks.derive_scenario(session.mode, session.scope, run_context)
        raw_prompt = run.prompt
        effective_prompt = apply_quick_action_prompt(
            raw_prompt,
            run.quick_action_id,
            session.interaction_locale,
        )
        turn_intent = classify_turn_intent(raw_prompt)
        evidence = (
            hooks.gather_evidence(
                db,
                novel,
                snapshot,
                run_context,
                interaction_locale=session.interaction_locale,
            )
            if should_preload_world_context(turn_intent)
            else []
        )
        persist_preloaded_evidence(db, run, evidence)

        session_data = {
            "mode": session.mode,
            "scope": session.scope,
            "context_json": run_context,
            "interaction_locale": session.interaction_locale,
            "display_title": session.display_title,
            "novel_id": novel_id,
        }
        inherited_workspace = run.workspace_json
        follow_up_messages, follow_up_workspace_seed = _build_follow_up_inputs(
            db,
            build_follow_up_conversation_messages=hooks.build_follow_up_conversation_messages,
            run=run,
            inherited_workspace=inherited_workspace,
        )

        def db_factory() -> Session:
            return SessionLocal()

        parsed, final_evidence, workspace, execution_mode, degraded_reason = (
            await _run_with_degradation(
                hooks,
                snapshot=snapshot,
                evidence=evidence,
                scenario=scenario,
                session_data=session_data,
                turn_intent=turn_intent,
                prompt=effective_prompt,
                llm_config=llm_config,
                user_id=user_id,
                run_id=run_id,
                worker_id=worker_id,
                db_factory=db_factory,
                inherited_workspace=inherited_workspace,
                prior_messages=follow_up_messages,
                workspace_seed=follow_up_workspace_seed,
            )
        )

        if parsed is None:
            parsed = {"answer": "", "suggestions": []}

        db_compile = db_factory()
        try:
            fresh_novel = db_compile.get(Novel, novel_id)
            fresh_snapshot = hooks.load_scope_snapshot(
                db_compile,
                fresh_novel or novel,
                session_data["mode"],
                session_data["scope"],
                session_data["context_json"],
            )
            compiled = hooks.compile_suggestions(
                parsed.get("suggestions", [])
                if should_preload_world_context(turn_intent)
                else [],
                final_evidence,
                fresh_snapshot,
                session_data["mode"],
                scenario,
                interaction_locale=session_data["interaction_locale"],
            )
        finally:
            db_compile.close()

        if not persist_completed_run(
            db_factory,
            run_id=run_id,
            worker_id=worker_id,
            answer=parsed.get("answer", ""),
            evidence=final_evidence,
            compiled_suggestions=compiled,
            workspace=workspace,
            execution_mode=execution_mode,
            degraded_reason=degraded_reason,
        ):
            logger.warning(
                "Skipping result persistence for run %s after lease loss", run_id
            )
    except hooks.lease_lost_error_type:
        return
    except Exception:
        logger.exception("Copilot run %s failed", run_id)
        try:
            err_db = SessionLocal()
            try:
                err_run = (
                    err_db.query(CopilotRun).filter(CopilotRun.run_id == run_id).first()
                )
                if err_run:
                    fail_run(
                        err_db,
                        err_run,
                        "run_execution_error",
                        copilot_run_failed_message(
                            resolve_run_interaction_locale(err_run)
                        ),
                        worker_id=worker_id,
                    )
            finally:
                err_db.close()
        except Exception:
            logger.exception("Failed to mark run %s as errored", run_id)
    finally:
        db.close()
