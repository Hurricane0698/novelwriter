# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Facade-safe adapter assembly for copilot runtime execution."""

from __future__ import annotations

from typing import Callable

import app.core.llm_semaphore as llm_semaphore_mod
from app.core.llm_config import ResolvedLlmConfig
from . import execution_runtime as execution_runtime_mod
from . import prompting as prompting_mod
from . import run_state as run_state_mod
from . import run_store as run_store_mod
from . import scope as scope_mod
from . import tool_loop as tool_loop_mod
from . import tracing as tracing_mod
from . import workspace as workspace_mod
from .research_tools import (
    RESEARCH_TOOL_CATALOG,
    dispatch_tool as _dispatch_tool,
    tool_load_scope_snapshot as _tool_load_scope_snapshot,
)
from .runtime_errors import RunLeaseLostError


async def run_tool_loop(
    db_factory,
    novel_id: int,
    session_data: dict,
    prompt: str,
    llm_config: ResolvedLlmConfig,
    user_id: int,
    snapshot,
    scenario: str,
    evidence: list,
    turn_intent: str,
    run_id: str = "",
    worker_id: str = "",
    inherited_workspace: dict | None = None,
    prior_messages: list[dict[str, str]] | None = None,
    workspace_seed: dict | None = None,
):
    deps = tool_loop_mod.ToolLoopDeps(
        tool_catalog=RESEARCH_TOOL_CATALOG,
        acquire_llm_slot=llm_semaphore_mod.acquire_llm_slot,
        release_llm_slot=llm_semaphore_mod.release_llm_slot,
        build_system_prompt=prompting_mod.build_tool_loop_system_prompt_build,
        build_auto_preload=prompting_mod.build_auto_preload,
        should_preload_world_context=prompting_mod.should_preload_world_context,
        load_scope_snapshot=scope_mod.load_scope_snapshot,
        dispatch_tool=_dispatch_tool,
        tool_load_scope_snapshot=_tool_load_scope_snapshot,
        persist_workspace=run_store_mod.persist_running_workspace,
        renew_run_lease=run_store_mod.renew_run_lease,
        parse_llm_response=run_state_mod.parse_llm_response,
        evidence_from_workspace=workspace_mod.evidence_from_workspace,
        lease_lost_error_factory=RunLeaseLostError,
    )
    return await tool_loop_mod.run_tool_loop(
        deps=deps,
        db_factory=db_factory,
        novel_id=novel_id,
        session_data=session_data,
        prompt=prompt,
        llm_config=llm_config,
        user_id=user_id,
        snapshot=snapshot,
        scenario=scenario,
        evidence=evidence,
        turn_intent=turn_intent,
        run_id=run_id,
        worker_id=worker_id,
        inherited_workspace=inherited_workspace,
        prior_messages=prior_messages,
        workspace_seed=workspace_seed,
        build_tool_journal_entry=tracing_mod.build_tool_journal_entry,
    )


async def run_one_shot(
    snapshot,
    evidence: list,
    scenario: str,
    session_data: dict,
    turn_intent: str,
    prompt: str,
    llm_config: ResolvedLlmConfig,
    user_id: int,
    *,
    run_id: str = "",
    worker_id: str = "",
    db_factory: Callable[[], object] | None = None,
):
    deps = execution_runtime_mod.OneShotDeps(
        acquire_llm_slot=llm_semaphore_mod.acquire_llm_slot,
        release_llm_slot=llm_semaphore_mod.release_llm_slot,
        renew_run_lease=run_store_mod.renew_run_lease,
        call_copilot_llm=run_state_mod.call_copilot_llm,
        parse_llm_response=run_state_mod.parse_llm_response,
        build_system_prompt=prompting_mod.build_copilot_system_prompt_build,
        lease_lost_error_factory=RunLeaseLostError,
    )
    return await execution_runtime_mod.run_one_shot(
        deps=deps,
        snapshot=snapshot,
        evidence=evidence,
        scenario=scenario,
        session_data=session_data,
        turn_intent=turn_intent,
        prompt=prompt,
        llm_config=llm_config,
        user_id=user_id,
        run_id=run_id,
        worker_id=worker_id,
        db_factory=db_factory,
    )
