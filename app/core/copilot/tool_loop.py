# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Tool-loop orchestration helpers for copilot."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from sqlalchemy.orm import Session

from app.core.ai_client import AIClient
from app.core.copilot.prompt_contract import PromptBuild
from app.core.copilot.run_state import ensure_run_lease as _ensure_run_lease
from app.core.copilot.scope import EvidenceItem, ScopeSnapshot
from app.core.copilot.tool_call_recovery import recover_tool_calls_from_text
from app.core.copilot.tool_contract import ResearchToolCatalog
from app.core.copilot.tool_runtime import (
    build_assistant_tool_call_message,
    execute_auto_open_for_progressive_disclosure,
)
from app.core.copilot.workspace import (
    Workspace,
    deserialize_tool_call,
    serialize_tool_call,
)
from app.models import Novel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolLoopDeps:
    tool_catalog: ResearchToolCatalog
    acquire_llm_slot: Callable[[], Awaitable[Any]]
    release_llm_slot: Callable[[], None]
    build_system_prompt: Callable[
        [ScopeSnapshot, str, str, dict[str, Any], str], PromptBuild
    ]
    build_auto_preload: Callable[[ScopeSnapshot, str], str]
    should_preload_world_context: Callable[[str], bool]
    load_scope_snapshot: Callable[
        [Session, Novel, str, str, dict[str, Any] | None], ScopeSnapshot
    ]
    dispatch_tool: Callable[
        [str, dict[str, Any], Session, int, ScopeSnapshot, Workspace, str], str
    ]
    tool_load_scope_snapshot: Callable[[ScopeSnapshot], str]
    persist_workspace: Callable[..., bool]
    renew_run_lease: Callable[..., bool]
    extract_llm_kwargs: Callable[[dict[str, Any] | None], dict[str, Any]]
    parse_llm_response: Callable[[str], dict[str, Any]]
    evidence_from_workspace: Callable[
        [Workspace, list[EvidenceItem], str], list[EvidenceItem]
    ]
    lease_lost_error_factory: Callable[[str], Exception]
    client_factory: Callable[[], AIClient] = AIClient




def _execute_pending_tool_calls(
    *,
    deps: ToolLoopDeps,
    build_tool_journal_entry: Callable[..., dict[str, Any]],
    db_factory: Callable[[], Session],
    novel_id: int,
    session_data: dict[str, Any],
    snapshot: ScopeSnapshot,
    workspace: Workspace,
    messages: list[dict[str, Any]],
    round_number: int,
    run_id: str = "",
    worker_id: str = "",
) -> ScopeSnapshot:
    while workspace.pending_tool_calls:
        _ensure_run_lease(deps, db_factory, run_id=run_id, worker_id=worker_id)

        tool_call = deserialize_tool_call(workspace.pending_tool_calls[0])
        workspace.tool_call_count += 1

        try:
            tool_args = json.loads(tool_call.arguments) if tool_call.arguments else {}
        except json.JSONDecodeError:
            tool_args = {}
        tool_spec = deps.tool_catalog.get(tool_call.name)

        tool_db = db_factory()
        try:
            if (
                tool_spec is not None
                and tool_spec.runtime.execution_path == "runtime"
                and tool_spec.name == "load_scope_snapshot"
            ):
                tool_novel = tool_db.get(Novel, novel_id)
                if tool_novel:
                    snapshot = deps.load_scope_snapshot(
                        tool_db,
                        tool_novel,
                        session_data["mode"],
                        session_data["scope"],
                        session_data["context_json"],
                    )
                tool_result = deps.tool_load_scope_snapshot(snapshot)
            else:
                tool_result = deps.dispatch_tool(
                    tool_call.name,
                    tool_args,
                    tool_db,
                    novel_id,
                    snapshot,
                    workspace,
                    session_data["interaction_locale"],
                )
        finally:
            tool_db.close()

        messages.append(
            {"role": "tool", "tool_call_id": tool_call.id, "content": tool_result}
        )
        workspace.tool_journal.append(
                build_tool_journal_entry(
                    tool_name=tool_call.name,
                    tool_args=tool_args,
                    tool_result=tool_result,
                    round_number=round_number,
                    call_index=workspace.tool_call_count,
                    interaction_locale=session_data["interaction_locale"],
                    tool_metadata=(
                        tool_spec.runtime.to_debug_dict() if tool_spec is not None else None
                    ),
                )
        )
        workspace.pending_tool_calls.pop(0)
        workspace.messages = list(messages)
        execute_auto_open_for_progressive_disclosure(
            dispatch_tool=deps.dispatch_tool,
            build_tool_journal_entry=build_tool_journal_entry,
            tool_db=tool_db,
            novel_id=novel_id,
            session_data=session_data,
            snapshot=snapshot,
            workspace=workspace,
            messages=messages,
            round_number=round_number,
            trigger_tool_spec=tool_spec,
            trigger_tool_result=tool_result,
        )

        if run_id and not deps.persist_workspace(
            db_factory, run_id, workspace, worker_id=worker_id
        ):
            raise deps.lease_lost_error_factory(run_id)

    return snapshot


async def run_tool_loop(
    *,
    deps: ToolLoopDeps,
    db_factory: Callable[[], Session],
    novel_id: int,
    session_data: dict[str, Any],
    prompt: str,
    llm_config: dict[str, Any] | None,
    user_id: int,
    snapshot: ScopeSnapshot,
    scenario: str,
    evidence: list[EvidenceItem],
    turn_intent: str,
    run_id: str = "",
    worker_id: str = "",
    inherited_workspace: dict[str, Any] | None = None,
    prior_messages: list[dict[str, str]] | None = None,
    workspace_seed: dict[str, Any] | None = None,
    build_tool_journal_entry: Callable[..., dict[str, Any]],
) -> tuple[dict[str, Any], list[EvidenceItem], Workspace]:
    """Run the tool-loop agent. Returns (parsed_answer, evidence, workspace)."""
    from app.config import get_settings

    settings = get_settings()
    max_rounds = settings.copilot_max_tool_rounds
    client = deps.client_factory()
    llm_kwargs = deps.extract_llm_kwargs(llm_config)
    valid_tool_names = {spec.name for spec in deps.tool_catalog.specs}

    if inherited_workspace and inherited_workspace.get("messages"):
        workspace = Workspace.from_dict(inherited_workspace)
        messages = list(workspace.messages)
        rounds_used = workspace.round_count
        logger.info(
            "Resuming tool loop from workspace: %d rounds used, %d packs, %d journal entries",
            rounds_used,
            len(workspace.evidence_packs),
            len(workspace.tool_journal),
        )
    else:
        workspace = (
            Workspace.from_dict(workspace_seed) if workspace_seed else Workspace()
        )
        workspace.tool_journal = []
        workspace.messages = []
        workspace.pending_tool_calls = []
        workspace.tool_call_count = 0
        workspace.round_count = 0
        workspace.final_answer_draft = None
        rounds_used = 0

        prompt_build = deps.build_system_prompt(
            snapshot,
            scenario,
            session_data["interaction_locale"],
            session_data,
            turn_intent,
        )
        workspace.prompt_debug = {
            "system_prompt": prompt_build.to_debug_dict(),
        }
        user_content = prompt
        if deps.should_preload_world_context(turn_intent):
            auto_preload = deps.build_auto_preload(
                snapshot, session_data["interaction_locale"]
            )
            workspace.prompt_debug["auto_preload"] = {
                "included": True,
                "character_count": len(auto_preload),
                "content_kind": "dynamic",
                "depends_on": ["snapshot.profile", "snapshot.scope_workset"],
            }
            user_content = (
                f"{prompt}\n\n---\n[Auto-preloaded world model summary]\n{auto_preload}"
            )
        else:
            workspace.prompt_debug["auto_preload"] = {
                "included": False,
                "character_count": 0,
                "content_kind": "dynamic",
                "depends_on": ["turn_intent"],
            }
        messages = [{"role": "system", "content": prompt_build.prompt_text}]
        if prior_messages:
            messages.extend(prior_messages)
        messages.append({"role": "user", "content": user_content})
        workspace.messages = list(messages)

    remaining_rounds = max(0, max_rounds - rounds_used)

    if workspace.pending_tool_calls:
        logger.info(
            "Resuming pending tool batch with %d remaining call(s)",
            len(workspace.pending_tool_calls),
        )
        snapshot = _execute_pending_tool_calls(
            deps=deps,
            build_tool_journal_entry=build_tool_journal_entry,
            db_factory=db_factory,
            novel_id=novel_id,
            session_data=session_data,
            snapshot=snapshot,
            workspace=workspace,
            messages=messages,
            round_number=max(1, workspace.round_count),
            run_id=run_id,
            worker_id=worker_id,
        )

    for round_idx in range(remaining_rounds):
        workspace.round_count = rounds_used + round_idx + 1
        _ensure_run_lease(deps, db_factory, run_id=run_id, worker_id=worker_id)

        await deps.acquire_llm_slot()
        try:
            response = await client.generate_with_tools(
                messages=messages,
                tools=deps.tool_catalog.tool_schemas,
                max_tokens=4000,
                temperature=0.4,
                role="default",
                user_id=user_id,
                **llm_kwargs,
            )
        finally:
            deps.release_llm_slot()

        _ensure_run_lease(deps, db_factory, run_id=run_id, worker_id=worker_id)

        tool_calls = response.tool_calls
        recovered_from_text = False
        if not tool_calls:
            recovered = recover_tool_calls_from_text(
                response.content, valid_tool_names
            )
            if recovered:
                logger.warning(
                    "Tool loop recovered %d text-form tool call(s) at round %d; "
                    "gateway returned tool calls as plain text",
                    len(recovered),
                    workspace.round_count,
                )
                tool_calls = recovered
                recovered_from_text = True

        if not tool_calls:
            parsed = deps.parse_llm_response(response.content or "")
            workspace.final_answer_draft = response.content
            if response.content:
                messages.append({"role": "assistant", "content": response.content})
            workspace.messages = list(messages)
            return (
                parsed,
                deps.evidence_from_workspace(
                    workspace, evidence, session_data["interaction_locale"]
                ),
                workspace,
            )

        messages.append(
            build_assistant_tool_call_message(
                tool_calls,
                # When the call was recovered from text, the original content was
                # the tool-call markup itself; drop it so history stays clean and
                # providers do not reject a content+tool_calls assistant message.
                content=None if recovered_from_text else response.content,
            )
        )
        workspace.pending_tool_calls = [
            serialize_tool_call(tool_call) for tool_call in tool_calls
        ]
        workspace.messages = list(messages)

        if run_id and not deps.persist_workspace(
            db_factory, run_id, workspace, worker_id=worker_id
        ):
            raise deps.lease_lost_error_factory(run_id)

        snapshot = _execute_pending_tool_calls(
            deps=deps,
            build_tool_journal_entry=build_tool_journal_entry,
            db_factory=db_factory,
            novel_id=novel_id,
            session_data=session_data,
            snapshot=snapshot,
            workspace=workspace,
            messages=messages,
            round_number=round_idx + 1,
            run_id=run_id,
            worker_id=worker_id,
        )

    _ensure_run_lease(deps, db_factory, run_id=run_id, worker_id=worker_id)
    await deps.acquire_llm_slot()
    try:
            response = await client.generate_with_tools(
                messages=messages,
                tools=deps.tool_catalog.tool_schemas,
                max_tokens=4000,
                temperature=0.4,
                role="default",
            user_id=user_id,
            tool_choice="none",
            **llm_kwargs,
        )
    finally:
        deps.release_llm_slot()

    _ensure_run_lease(deps, db_factory, run_id=run_id, worker_id=worker_id)

    parsed = deps.parse_llm_response(response.content or "")
    workspace.final_answer_draft = response.content
    if response.content:
        messages.append({"role": "assistant", "content": response.content})
    workspace.messages = list(messages)
    return (
        parsed,
        deps.evidence_from_workspace(
            workspace, evidence, session_data["interaction_locale"]
        ),
        workspace,
    )
