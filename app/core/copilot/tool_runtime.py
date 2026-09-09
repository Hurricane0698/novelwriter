# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared runtime helpers for copilot tool-loop execution."""

from __future__ import annotations

import json
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.ai_client import ToolCall
from app.core.copilot.scope import ScopeSnapshot
from app.core.copilot.sync_runtime import check_sync_cancelled
from app.core.copilot.tool_contract import ResearchToolSpec
from app.core.copilot.research_tools import get_research_tool_spec
from app.core.copilot.workspace import Workspace

_AUTO_OPEN_EXPAND_CHARS = 2000


def build_assistant_tool_call_message(
    tool_calls: list[ToolCall],
    *,
    content: str | None,
) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": content or "",
        "tool_calls": [
            {
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.name,
                    "arguments": tool_call.arguments,
                },
            }
            for tool_call in tool_calls
        ],
    }


def select_progressive_disclosure_pack_id(
    *,
    tool_spec: ResearchToolSpec | None,
    tool_result: str,
    session_data: dict[str, Any],
    workspace: Workspace,
) -> str | None:
    if (
        tool_spec is None
        or tool_spec.runtime.auto_follow_up_hint != "open_first_chapter_pack"
    ):
        return None
    if session_data.get("scope") != "current_entity":
        return None
    if workspace.opened_pack_ids:
        return None

    payload = None
    try:
        payload = json.loads(tool_result)
    except json.JSONDecodeError:
        payload = None
    if not isinstance(payload, dict):
        return None

    raw_packs = payload.get("packs")
    if not isinstance(raw_packs, list):
        return None

    pack_ids = [
        str(item.get("pack_id") or "").strip()
        for item in raw_packs
        if isinstance(item, dict) and str(item.get("pack_id") or "").strip()
    ]
    for pack_id in pack_ids:
        pack = workspace.evidence_packs.get(pack_id)
        if not pack:
            continue
        if any(ref.get("type") == "chapter" for ref in pack.source_refs):
            return pack_id
    return None


def execute_auto_open_for_progressive_disclosure(
    *,
    dispatch_tool: Callable[
        [str, dict[str, Any], Session, int, ScopeSnapshot, Workspace, str], str
    ],
    build_tool_journal_entry: Callable[..., dict[str, Any]],
    tool_db: Session,
    novel_id: int,
    session_data: dict[str, Any],
    snapshot: ScopeSnapshot,
    workspace: Workspace,
    messages: list[dict[str, Any]],
    round_number: int,
    trigger_tool_spec: ResearchToolSpec | None,
    trigger_tool_result: str,
) -> None:
    pack_id = select_progressive_disclosure_pack_id(
        tool_spec=trigger_tool_spec,
        tool_result=trigger_tool_result,
        session_data=session_data,
        workspace=workspace,
    )
    if not pack_id:
        return

    check_sync_cancelled()
    workspace.tool_call_count += 1
    auto_tool_call = ToolCall(
        id=f"auto_open_{workspace.tool_call_count}",
        name="open",
        arguments=json.dumps(
            {"pack_id": pack_id, "expand_chars": _AUTO_OPEN_EXPAND_CHARS},
            ensure_ascii=False,
        ),
    )
    messages.append(
        build_assistant_tool_call_message(
            [auto_tool_call],
            content="",
        )
    )
    open_result = dispatch_tool(
        "open",
        {"pack_id": pack_id, "expand_chars": _AUTO_OPEN_EXPAND_CHARS},
        tool_db,
        novel_id,
        snapshot,
        workspace,
        session_data["interaction_locale"],
    )
    check_sync_cancelled()
    messages.append(
        {
            "role": "tool",
            "tool_call_id": auto_tool_call.id,
            "content": open_result,
        }
    )
    workspace.tool_journal.append(
        build_tool_journal_entry(
            tool_name="open",
            tool_args={"pack_id": pack_id, "expand_chars": _AUTO_OPEN_EXPAND_CHARS},
            tool_result=open_result,
            round_number=round_number,
            call_index=workspace.tool_call_count,
            interaction_locale=session_data["interaction_locale"],
            tool_metadata=(
                get_research_tool_spec("open").runtime.to_debug_dict()
                if get_research_tool_spec("open") is not None
                else None
            ),
        )
    )
    workspace.messages = list(messages)
