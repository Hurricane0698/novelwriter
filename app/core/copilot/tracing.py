# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Tool-loop journal and trace helpers for copilot."""

from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

from app.core.copilot.messages import CopilotTextKey, get_copilot_text

if TYPE_CHECKING:
    from app.core.copilot.workspace import Workspace


def _truncate_trace_text(value: str, limit: int = 48) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit - 1]}…"


def _maybe_parse_json_object(raw: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _tool_kind_for_name(tool_name: str) -> str:
    return {
        "find": "tool_find",
        "open": "tool_open",
        "open_many": "tool_open",
        "read": "tool_read",
        "load_scope_snapshot": "tool_load_scope_snapshot",
    }.get(tool_name, "tool_other")


def _extract_tool_trace_error(
    *,
    tool_name: str,
    payload: dict[str, Any],
) -> str | None:
    top_level_error = payload.get("error")
    if isinstance(top_level_error, str) and top_level_error.strip():
        return top_level_error

    if tool_name == "open_many":
        results = payload.get("results")
        if isinstance(results, list):
            for item in results:
                if not isinstance(item, dict):
                    continue
                item_error = item.get("error")
                if isinstance(item_error, str) and item_error.strip():
                    return item_error
    return None


def _build_tool_trace_summary(
    tool_name: str,
    tool_args: dict[str, Any],
    tool_result: str,
    interaction_locale: str,
    *,
    payload: dict[str, Any] | None = None,
    trace_error: str | None = None,
) -> str:
    payload = payload or _maybe_parse_json_object(tool_result) or {}
    if trace_error:
        return get_copilot_text(
            CopilotTextKey.TRACE_RETRIEVAL_STEP_INCOMPLETE,
            locale=interaction_locale,
            error=_truncate_trace_text(trace_error, limit=64),
        )

    if tool_name == "find":
        query = _truncate_trace_text(
            str(
                tool_args.get("query", "")
                or get_copilot_text(CopilotTextKey.TRACE_EMPTY_QUERY, locale=interaction_locale)
            ),
        )
        scope = str(tool_args.get("scope", "all") or "all")
        total_found = payload.get("total_found")
        summary = get_copilot_text(
            CopilotTextKey.TRACE_FIND,
            locale=interaction_locale,
            query=query,
        )
        if scope != "all":
            summary += get_copilot_text(
                CopilotTextKey.TRACE_FIND_SCOPE_SUFFIX,
                locale=interaction_locale,
                scope=scope,
            )
        if isinstance(total_found, int):
            summary += get_copilot_text(
                CopilotTextKey.TRACE_FIND_TOTAL_SUFFIX,
                locale=interaction_locale,
                count=total_found,
            )
        return summary

    if tool_name == "open":
        source_refs = payload.get("source_refs")
        source_count = len(source_refs) if isinstance(source_refs, list) else None
        summary = get_copilot_text(
            CopilotTextKey.TRACE_OPEN,
            locale=interaction_locale,
        )
        if source_count is not None:
            summary += get_copilot_text(
                CopilotTextKey.TRACE_OPEN_SOURCE_SUFFIX,
                locale=interaction_locale,
                count=source_count,
            )
        return summary

    if tool_name == "open_many":
        opened_count = payload.get("opened_count")
        summary = get_copilot_text(
            CopilotTextKey.TRACE_OPEN,
            locale=interaction_locale,
        )
        if isinstance(opened_count, int):
            summary += get_copilot_text(
                CopilotTextKey.TRACE_OPEN_SOURCE_SUFFIX,
                locale=interaction_locale,
                count=opened_count,
            )
        return summary

    if tool_name == "read":
        target_refs = tool_args.get("target_refs")
        target_count = len(target_refs) if isinstance(target_refs, list) else 0
        results = payload.get("results")
        result_count = len(results) if isinstance(results, list) else None
        summary = get_copilot_text(
            CopilotTextKey.TRACE_READ_TARGETS,
            locale=interaction_locale,
            count=target_count,
        )
        if result_count is not None:
            summary += get_copilot_text(
                CopilotTextKey.TRACE_READ_RESULTS_SUFFIX,
                locale=interaction_locale,
                count=result_count,
            )
        return summary

    if tool_name == "load_scope_snapshot":
        entity_count = payload.get("entity_count")
        relationship_count = payload.get("relationship_count")
        draft_count = payload.get("draft_count")
        parts = []
        if isinstance(entity_count, int):
            parts.append(get_copilot_text(CopilotTextKey.TRACE_REFRESH_ENTITIES, locale=interaction_locale, count=entity_count))
        if isinstance(relationship_count, int):
            parts.append(get_copilot_text(CopilotTextKey.TRACE_REFRESH_RELATIONSHIPS, locale=interaction_locale, count=relationship_count))
        if isinstance(draft_count, int):
            parts.append(get_copilot_text(CopilotTextKey.TRACE_REFRESH_DRAFTS, locale=interaction_locale, count=draft_count))

        summary = get_copilot_text(
            CopilotTextKey.TRACE_REFRESH_SNAPSHOT,
            locale=interaction_locale,
        )
        if parts:
            summary += get_copilot_text(
                CopilotTextKey.TRACE_REFRESH_COUNTS_SUFFIX,
                locale=interaction_locale,
                counts=" / ".join(parts),
            )
        else:
            summary += get_copilot_text(
                CopilotTextKey.TRACE_REFRESH_CONTEXT_REFRESHED_SUFFIX,
                locale=interaction_locale,
            )
        return summary

    return get_copilot_text(
        CopilotTextKey.TRACE_GENERIC_TOOL_COMPLETED,
        locale=interaction_locale,
        tool_name=tool_name,
    )


def build_tool_journal_entry(
    *,
    tool_name: str,
    tool_args: dict[str, Any],
    tool_result: str,
    round_number: int,
    call_index: int,
    interaction_locale: str = "zh",
    tool_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = _maybe_parse_json_object(tool_result) or {}
    trace_error = _extract_tool_trace_error(tool_name=tool_name, payload=payload)
    entry = {
        "step_id": f"tool_{call_index}",
        "kind": _tool_kind_for_name(tool_name),
        "status": "incomplete" if trace_error else "completed",
        "summary": _build_tool_trace_summary(
            tool_name,
            tool_args,
            tool_result,
            interaction_locale,
            payload=payload,
            trace_error=trace_error,
        ),
        "tool": tool_name,
        "args": tool_args,
        "result_summary": tool_result[:200],
        "round": round_number,
    }
    if tool_metadata:
        entry["tool_metadata"] = tool_metadata
    return entry


def _build_trace_from_tool_journal(workspace: Workspace, interaction_locale: str) -> list[dict[str, Any]]:
    trace_steps: list[dict[str, Any]] = []
    tool_calls = max(0, workspace.tool_call_count)
    if tool_calls > 0:
        trace_steps.append({
            "step_id": "tool_mode",
            "kind": "tool_mode",
            "status": "completed",
            "summary": get_copilot_text(
                CopilotTextKey.TRACE_TOOL_MODE_USED_STEPS,
                locale=interaction_locale,
                count=tool_calls,
            ),
        })
    else:
        trace_steps.append({
            "step_id": "tool_mode",
            "kind": "tool_mode",
            "status": "completed",
            "summary": get_copilot_text(
                CopilotTextKey.TRACE_TOOL_MODE_DIRECT,
                locale=interaction_locale,
            ),
        })

    for index, entry in enumerate(workspace.tool_journal, start=1):
        trace_steps.append({
            "step_id": entry.get("step_id", f"tool_{index}"),
            "kind": entry.get("kind", _tool_kind_for_name(str(entry.get("tool", "")))),
            "status": entry.get("status", "completed"),
            "summary": entry.get("summary") or get_copilot_text(
                CopilotTextKey.TRACE_TOOL_COMPLETED_FALLBACK,
                locale=interaction_locale,
                tool_name=entry.get("tool", "unknown"),
            ),
        })

    return trace_steps


def build_running_trace(workspace: Workspace, interaction_locale: str = "zh") -> list[dict[str, Any]]:
    trace_steps = _build_trace_from_tool_journal(workspace, interaction_locale)
    trace_steps.append({
        "step_id": "analyze_running",
        "kind": "analyze",
        "status": "running",
        "summary": get_copilot_text(
            CopilotTextKey.TRACE_ANALYZE_RUNNING,
            locale=interaction_locale,
        ),
    })
    return trace_steps


def build_completed_trace(
    *,
    workspace: Workspace | None,
    execution_mode: str,
    degraded_reason: str | None,
    evidence_count: int,
    suggestion_count: int,
    interaction_locale: str = "zh",
) -> list[dict[str, Any]]:
    trace_steps: list[dict[str, Any]] = []

    if execution_mode == "tool_loop":
        if workspace is not None:
            trace_steps.extend(_build_trace_from_tool_journal(workspace, interaction_locale))
        else:
            trace_steps.append({
                "step_id": "tool_mode",
                "kind": "tool_mode",
                "status": "completed",
                "summary": get_copilot_text(
                    CopilotTextKey.TRACE_TOOL_LOOP_COMPLETED,
                    locale=interaction_locale,
                ),
            })
    elif execution_mode == "one_shot_unsupported":
        trace_steps.append({
            "step_id": "tool_mode",
            "kind": "tool_mode",
            "status": "completed",
            "summary": get_copilot_text(
                CopilotTextKey.TRACE_ONE_SHOT_UNSUPPORTED,
                locale=interaction_locale,
            ),
        })
    elif execution_mode == "one_shot_fallback":
        reason = _truncate_trace_text(degraded_reason or "tool_loop_failed", limit=44)
        trace_steps.append({
            "step_id": "tool_mode",
            "kind": "tool_mode",
            "status": "completed",
            "summary": get_copilot_text(
                CopilotTextKey.TRACE_ONE_SHOT_FAILED,
                locale=interaction_locale,
                reason=reason,
            ),
        })

    trace_steps.append({
        "step_id": "evidence_complete",
        "kind": "evidence",
        "status": "completed",
        "summary": get_copilot_text(
            CopilotTextKey.TRACE_EVIDENCE_PREPARED,
            locale=interaction_locale,
            count=evidence_count,
        ),
    })
    trace_steps.append({
        "step_id": "analyze_complete",
        "kind": "analyze",
        "status": "completed",
        "summary": get_copilot_text(
            CopilotTextKey.TRACE_ANALYSIS_COMPLETED,
            locale=interaction_locale,
            count=suggestion_count,
        ),
    })
    return trace_steps
