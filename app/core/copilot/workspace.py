# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Workspace state and evidence-pack helpers for copilot."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session, load_only

from app.core.ai_client import ToolCall
from app.core.copilot.messages import CopilotTextKey, get_copilot_text
from app.core.copilot.scope import EvidenceItem, MAX_EVIDENCE_ITEMS
from app.core.copilot.session_runtime import build_follow_up_conversation_messages
from app.models import CopilotRun


@dataclass
class EvidencePack:
    pack_id: str
    source_refs: list[dict[str, Any]]
    preview_excerpt: str
    anchor_terms: list[str]
    support_count: int
    related_targets: list[dict[str, Any]]
    conflict_group: str | None = None
    expanded_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "pack_id": self.pack_id,
            "source_refs": self.source_refs,
            "preview_excerpt": self.preview_excerpt,
            "anchor_terms": self.anchor_terms,
            "support_count": self.support_count,
            "related_targets": self.related_targets,
            "conflict_group": self.conflict_group,
            "expanded_text": self.expanded_text,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> EvidencePack:
        return cls(
            pack_id=payload["pack_id"],
            source_refs=payload.get("source_refs", []),
            preview_excerpt=payload.get("preview_excerpt", ""),
            anchor_terms=payload.get("anchor_terms", []),
            support_count=payload.get("support_count", 0),
            related_targets=payload.get("related_targets", []),
            conflict_group=payload.get("conflict_group"),
            expanded_text=payload.get("expanded_text"),
        )


def make_pack_id(prefix: str, *parts: Any) -> str:
    """Build a stable pack ID including a content hash suffix."""
    content = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(content.encode()).hexdigest()[:8]
    return f"{prefix}_{digest}"


def _workspace_text(
    interaction_locale: str,
    text_key: CopilotTextKey,
    **params: object,
) -> str:
    return get_copilot_text(text_key, locale=interaction_locale, **params)


@dataclass
class Workspace:
    evidence_packs: dict[str, EvidencePack] = field(default_factory=dict)
    tool_journal: list[dict[str, Any]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    opened_pack_ids: list[str] = field(default_factory=list)
    pending_tool_calls: list[dict[str, str]] = field(default_factory=list)
    tool_call_count: int = 0
    round_count: int = 0
    snapshot_fingerprint: str = ""
    final_answer_draft: str | None = None
    prompt_debug: dict[str, Any] | None = None
    history: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "evidence_packs": {key: value.to_dict() for key, value in self.evidence_packs.items()},
            "tool_journal": self.tool_journal,
            "messages": self.messages,
            "opened_pack_ids": self.opened_pack_ids,
            "pending_tool_calls": self.pending_tool_calls,
            "tool_call_count": self.tool_call_count,
            "round_count": self.round_count,
            "snapshot_fingerprint": self.snapshot_fingerprint,
            "final_answer_draft": self.final_answer_draft,
            "prompt_debug": self.prompt_debug,
        }
        if self.history is not None:
            payload["history"] = deepcopy(self.history)
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Workspace:
        packs = {
            key: EvidencePack.from_dict(value)
            for key, value in payload.get("evidence_packs", {}).items()
        }
        return cls(
            evidence_packs=packs,
            tool_journal=payload.get("tool_journal", []),
            messages=payload.get("messages", []),
            opened_pack_ids=payload.get("opened_pack_ids", []),
            pending_tool_calls=payload.get("pending_tool_calls", []),
            tool_call_count=payload.get("tool_call_count", 0),
            round_count=payload.get("round_count", 0),
            snapshot_fingerprint=payload.get("snapshot_fingerprint", ""),
            final_answer_draft=payload.get("final_answer_draft"),
            prompt_debug=payload.get("prompt_debug"),
            history=deepcopy(payload.get("history")),
        )


def _history_digest(messages: list[dict[str, Any]]) -> str:
    encoded = json.dumps(
        messages, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_history(history: object) -> tuple[list[int], int, str]:
    if not isinstance(history, dict):
        raise ValueError("Workspace history metadata is missing")
    ids = history.get("run_ids")
    count = history.get("message_count")
    digest = history.get("sha256")
    if (
        not isinstance(ids, list)
        or any(type(value) is not int or value <= 0 for value in ids)
        or len(set(ids)) != len(ids)
        or type(count) is not int
        or count < 0
        or not isinstance(digest, str)
        or len(digest) != 64
    ):
        raise ValueError("Workspace history metadata is invalid")
    return ids, count, digest


def workspace_to_storage(workspace: Workspace) -> dict[str, Any]:
    """Store the current turn and frozen history references, without truncation.

    Legacy resumed workspaces have no references; preserve their full messages.
    Runtime serialization via to_dict() always retains the full model context.
    """
    payload = workspace.to_dict()
    if workspace.history is None:
        return payload
    _, count, digest = _validate_history(workspace.history)
    messages = workspace.messages
    if (
        not messages
        or not isinstance(messages[0], dict)
        or messages[0].get("role") != "system"
        or _history_digest(messages[1:1 + count]) != digest
        or len(messages) < 1 + count
    ):
        raise ValueError("Workspace history no longer matches the model messages")
    payload["storage_version"] = 2
    payload["messages"] = [messages[0], *messages[1 + count:]]
    return payload


def load_run_workspace(db: Session, run: CopilotRun) -> dict[str, Any] | None:
    """Expand a persisted workspace while its owning database session is open."""
    payload = run.workspace_json
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise ValueError("Workspace payload is invalid")
    if "storage_version" not in payload:
        return payload
    if payload["storage_version"] != 2:
        raise ValueError("Workspace history storage version is unsupported")

    ids, count, digest = _validate_history(payload.get("history"))
    rows_by_id: dict[int, CopilotRun] = {}
    for offset in range(0, len(ids), 500):
        rows = (
            db.query(CopilotRun)
            .options(load_only(CopilotRun.status, CopilotRun.prompt, CopilotRun.answer))
            .filter(
                CopilotRun.id.in_(ids[offset:offset + 500]),
                CopilotRun.copilot_session_id == run.copilot_session_id,
                CopilotRun.novel_id == run.novel_id,
                CopilotRun.user_id == run.user_id,
                CopilotRun.status == "completed",
            )
            .all()
        )
        rows_by_id.update((row.id, row) for row in rows)
    if len(rows_by_id) != len(ids):
        raise ValueError("Workspace history is unavailable or outside this session")
    history = build_follow_up_conversation_messages([rows_by_id[row_id] for row_id in ids])
    if len(history) != count or _history_digest(history) != digest:
        raise ValueError("Workspace history changed after this turn was prepared")
    messages = payload.get("messages")
    if (
        not isinstance(messages, list)
        or not messages
        or not isinstance(messages[0], dict)
        or messages[0].get("role") != "system"
    ):
        raise ValueError("Workspace history insertion point is invalid")
    restored = dict(payload)
    restored.pop("storage_version")
    restored["messages"] = [messages[0], *history, *messages[1:]]
    return restored


def serialize_tool_call(tool_call: ToolCall) -> dict[str, str]:
    return {
        "id": tool_call.id,
        "name": tool_call.name,
        "arguments": tool_call.arguments,
    }


def deserialize_tool_call(payload: dict[str, Any]) -> ToolCall:
    return ToolCall(
        id=str(payload.get("id") or ""),
        name=str(payload.get("name") or ""),
        arguments=str(payload.get("arguments") or ""),
    )


def build_follow_up_workspace_seed(
    workspace_payload: dict[str, Any] | None,
    *,
    history_runs: Sequence[CopilotRun] | None = None,
) -> dict[str, Any] | None:
    """Carry reusable research memory into a fresh follow-up run.

    Follow-up runs should inherit evidence-pack memory but not stale pending
    tool calls, exhausted round counters, or old assistant drafts. Those are
    run-scoped, not session-scoped.
    """
    if not workspace_payload and not history_runs:
        return None

    prior_workspace = Workspace.from_dict(workspace_payload or {})
    completed = [row for row in history_runs or () if row.status == "completed"]
    messages = build_follow_up_conversation_messages(completed)
    history = (
        {
            "run_ids": [row.id for row in completed],
            "message_count": len(messages),
            "sha256": _history_digest(messages),
        }
        if history_runs is not None
        else None
    )
    return Workspace(
        evidence_packs=dict(prior_workspace.evidence_packs),
        opened_pack_ids=list(prior_workspace.opened_pack_ids),
        snapshot_fingerprint=prior_workspace.snapshot_fingerprint,
        history=history,
    ).to_dict()


def evidence_from_workspace(
    workspace: Workspace,
    base_evidence: list[EvidenceItem],
    interaction_locale: str = "zh",
) -> list[EvidenceItem]:
    """Merge tool-discovered evidence packs into the frontend evidence list."""
    seen_ids = {evidence.evidence_id for evidence in base_evidence}
    merged = list(base_evidence)
    opened_pack_ids = set(workspace.opened_pack_ids)

    for pack in workspace.evidence_packs.values():
        evidence_id = f"pack_{pack.pack_id}"
        if evidence_id in seen_ids:
            continue
        seen_ids.add(evidence_id)

        source_type = "evidence_pack"
        source_ref: dict[str, Any] = {}
        if pack.source_refs:
            first_ref = pack.source_refs[0]
            ref_type = first_ref.get("type", "")
            if ref_type == "chapter":
                source_type = "chapter_excerpt"
                source_ref = {
                    "chapter_id": first_ref.get("chapter_id"),
                    "chapter_number": first_ref.get("chapter_number"),
                    "start_pos": first_ref.get("start_pos", 0),
                    "end_pos": first_ref.get("end_pos", 0),
                }
            elif ref_type == "entity":
                source_type = "world_entity"
                source_ref = {"entity_id": first_ref.get("id")}
            elif ref_type == "relationship":
                source_type = "world_relationship"
                source_ref = {"relationship_id": first_ref.get("id")}
            elif ref_type == "system":
                source_type = "world_system"
                source_ref = {"system_id": first_ref.get("id")}

        merged.append(EvidenceItem(
            evidence_id=evidence_id,
            source_type=source_type,
            source_ref=source_ref,
            title=", ".join(pack.anchor_terms[:3]) or pack.pack_id,
            excerpt=pack.expanded_text or pack.preview_excerpt,
            why_relevant=(
                _workspace_text(
                    interaction_locale,
                    CopilotTextKey.WORKSPACE_EVIDENCE_COMPILED_MULTIPLE,
                    count=pack.support_count,
                )
                if pack.support_count and pack.support_count > 1
                else _workspace_text(interaction_locale, CopilotTextKey.WORKSPACE_EVIDENCE_COMPILED)
            ),
            pack_id=pack.pack_id,
            source_refs=list(pack.source_refs),
            anchor_terms=list(pack.anchor_terms),
            support_count=pack.support_count,
            preview_excerpt=pack.preview_excerpt,
            expanded=pack.pack_id in opened_pack_ids,
        ))

    return merged[:MAX_EVIDENCE_ITEMS * 2]
