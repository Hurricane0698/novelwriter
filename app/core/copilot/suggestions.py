# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Suggestion compilation and dismissal helpers for copilot."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.copilot.messages import CopilotTextKey, get_copilot_text
from app.core.copilot.suggestion_actions import (
    build_create_action,
    build_entity_suggestion_candidates,
    build_non_actionable_create_reason,
    build_update_action,
    expand_relationship_entity_dependencies,
    resolve_target,
)
from app.core.copilot.scope import EvidenceItem, ScopeSnapshot
from app.models import CopilotRun

logger = logging.getLogger(__name__)

MAX_COMPILED_SUGGESTIONS = 20

_RESOURCE_TEXT_KEYS: dict[str, CopilotTextKey] = {
    "entity": CopilotTextKey.TEXT_RESOURCE_ENTITY,
    "relationship": CopilotTextKey.TEXT_RESOURCE_RELATIONSHIP,
    "system": CopilotTextKey.TEXT_RESOURCE_SYSTEM,
}

_FIELD_TEXT_KEYS: dict[str, CopilotTextKey] = {
    "name": CopilotTextKey.TEXT_FIELD_NAME,
    "entity_type": CopilotTextKey.TEXT_FIELD_ENTITY_TYPE,
    "description": CopilotTextKey.TEXT_FIELD_DESCRIPTION,
    "aliases": CopilotTextKey.TEXT_FIELD_ALIASES,
    "label": CopilotTextKey.TEXT_FIELD_RELATIONSHIP_LABEL,
    "visibility": CopilotTextKey.TEXT_FIELD_VISIBILITY,
    "constraints": CopilotTextKey.TEXT_FIELD_CONSTRAINTS,
    "display_type": CopilotTextKey.TEXT_FIELD_DISPLAY_TYPE,
}


def _suggestion_text(
    interaction_locale: str,
    text_key: CopilotTextKey,
    **params: object,
) -> str:
    return get_copilot_text(text_key, locale=interaction_locale, **params)


def _resource_label(resource: str, interaction_locale: str) -> str:
    key = _RESOURCE_TEXT_KEYS.get(resource)
    if key is None:
        return resource
    return _suggestion_text(interaction_locale, key)


@dataclass
class CompiledSuggestion:
    suggestion_id: str
    kind: str
    title: str
    summary: str
    evidence_ids: list[str]
    target: dict[str, Any]
    preview: dict[str, Any]
    apply_action: dict[str, Any] | None
    status: str = "pending"


def compile_suggestions(
    raw_suggestions: list[dict[str, Any]],
    evidence: list[EvidenceItem],
    snapshot: ScopeSnapshot,
    mode: str,
    scenario: str,
    interaction_locale: str = "zh",
) -> list[CompiledSuggestion]:
    """Backend-compile model-drafted suggestions into validated actionable cards."""
    limited_raw_suggestions = raw_suggestions[:MAX_COMPILED_SUGGESTIONS]
    expanded_raw_suggestions = expand_relationship_entity_dependencies(
        limited_raw_suggestions,
        snapshot,
        interaction_locale,
        suggestion_text=_suggestion_text,
    )
    suggestion_ids = [
        f"sg_{i}_{uuid.uuid4().hex[:8]}" for i, _ in enumerate(expanded_raw_suggestions)
    ]
    entity_candidates = build_entity_suggestion_candidates(
        expanded_raw_suggestions,
        suggestion_ids,
        language=snapshot.novel_language,
    )
    compiled: list[CompiledSuggestion] = []
    for index, raw in enumerate(expanded_raw_suggestions):
        try:
            suggestion = _compile_one(
                raw,
                index,
                suggestion_ids[index],
                evidence,
                snapshot,
                mode,
                scenario,
                entity_candidates,
                interaction_locale,
            )
            compiled.append(suggestion)
        except Exception:
            logger.debug("Failed to compile suggestion %d", index, exc_info=True)
    return compiled


def _compile_one(
    raw: dict[str, Any],
    index: int,
    suggestion_id: str,
    evidence: list[EvidenceItem],
    snapshot: ScopeSnapshot,
    mode: str,
    scenario: str,
    entity_candidates: dict[str, dict[str, Any]],
    interaction_locale: str,
) -> CompiledSuggestion:
    kind = raw.get("kind", "")
    title = raw.get(
        "title",
        _suggestion_text(
            interaction_locale,
            CopilotTextKey.SUGGESTION_FALLBACK_TITLE,
            index=index + 1,
        ),
    )
    summary = raw.get("summary", "")
    target_resource = raw.get("target_resource", "entity")
    is_draft_governance = (
        snapshot.profile == "draft_governance"
        or mode == "draft_cleanup"
        or scenario == "draft_cleanup"
    )
    target_id = raw.get("target_id")
    if isinstance(target_id, str):
        try:
            target_id = int(target_id)
        except (ValueError, TypeError):
            target_id = None
    delta = raw.get("delta") or {}

    cited = raw.get("cited_evidence_indices", [])
    evidence_ids = [
        evidence[idx].evidence_id
        for idx in cited
        if isinstance(idx, int) and 0 <= idx < len(evidence)
    ]
    evidence_quotes = [
        evidence[idx].excerpt[:200]
        for idx in cited
        if isinstance(idx, int) and 0 <= idx < len(evidence)
    ][:3]

    actionable = True
    apply_action = None
    target_label = ""
    non_actionable_reason: str | None = None

    if kind.startswith("update_"):
        resolved = resolve_target(target_resource, target_id, snapshot)
        if resolved is None:
            actionable = False
            target_label = str(target_id or "?")
            non_actionable_reason = _suggestion_text(
                interaction_locale, CopilotTextKey.SUGGESTION_REASON_STALE
            )
        else:
            target_id = resolved["id"]
            target_label = resolved["label"]
            if is_draft_governance and not resolved.get("is_draft", False):
                actionable = False
                non_actionable_reason = _suggestion_text(
                    interaction_locale,
                    CopilotTextKey.SUGGESTION_REASON_DRAFT_ONLY,
                )
            else:
                apply_action = build_update_action(
                    kind, delta, target_resource, target_id, snapshot, mode
                )
                if apply_action is None:
                    actionable = False
                    non_actionable_reason = _suggestion_text(
                        interaction_locale,
                        CopilotTextKey.SUGGESTION_REASON_CANNOT_APPLY_DIRECT,
                    )

    elif kind.startswith("create_"):
        if is_draft_governance:
            actionable = False
            non_actionable_reason = _suggestion_text(
                interaction_locale,
                CopilotTextKey.SUGGESTION_REASON_DRAFT_CREATE_DISALLOWED,
            )
        else:
            target_id = None
            target_label = (
                delta.get("name", "")
                or delta.get("label", "")
                or _build_new_resource_label(target_resource, interaction_locale)
            )
            apply_action = build_create_action(
                kind, delta, target_resource, snapshot, entity_candidates
            )
            if apply_action is None:
                actionable = False
                non_actionable_reason = build_non_actionable_create_reason(
                    kind,
                    delta,
                    target_resource,
                    snapshot,
                    entity_candidates,
                    interaction_locale,
                    suggestion_text=_suggestion_text,
                )
    else:
        actionable = False
        target_label = str(target_id or "?")
        non_actionable_reason = _suggestion_text(
            interaction_locale,
            CopilotTextKey.SUGGESTION_REASON_NOT_DIRECTLY_APPLICABLE,
        )

    field_deltas = _build_field_deltas(
        kind,
        delta,
        target_id,
        target_resource,
        snapshot,
        interaction_locale,
    )
    preview = {
        "target_label": target_label
        or _build_new_resource_label(target_resource, interaction_locale),
        "summary": summary,
        "field_deltas": field_deltas,
        "evidence_quotes": evidence_quotes,
        "actionable": actionable,
        "non_actionable_reason": non_actionable_reason,
    }

    target_tab = _resource_to_tab(
        target_resource,
        "draft_governance" if is_draft_governance else snapshot.profile,
    )
    target_dict: dict[str, Any] = {
        "resource": target_resource,
        "resource_id": target_id,
        "label": target_label or "",
        "tab": target_tab,
    }
    if target_resource == "entity":
        target_dict["entity_id"] = target_id
    elif target_resource == "relationship":
        if target_id:
            target_dict["highlight_id"] = target_id
            for relationship in snapshot.relationships:
                if relationship.id == target_id:
                    target_dict["entity_id"] = relationship.source_id
                    break
        elif isinstance(delta.get("source_id"), int):
            target_dict["entity_id"] = delta["source_id"]
        elif isinstance(delta.get("target_id"), int):
            target_dict["entity_id"] = delta["target_id"]
        elif isinstance(snapshot.focus_entity_id, int):
            target_dict["entity_id"] = snapshot.focus_entity_id
    if is_draft_governance:
        target_dict["tab"] = "review"
        target_dict["review_kind"] = _resource_to_review_kind(target_resource)
        if target_id:
            target_dict["highlight_id"] = target_id

    return CompiledSuggestion(
        suggestion_id=suggestion_id,
        kind=kind,
        title=title,
        summary=summary,
        evidence_ids=evidence_ids,
        target=target_dict,
        preview=preview,
        apply_action=apply_action,
    )


def _resource_to_tab(resource: str, profile: str) -> str:
    if profile == "draft_governance":
        return "review"
    return {
        "entity": "entities",
        "relationship": "relationships",
        "system": "systems",
    }.get(resource, "entities")


def _build_new_resource_label(resource: str, interaction_locale: str) -> str:
    return _suggestion_text(
        interaction_locale,
        CopilotTextKey.TEXT_NEW_RESOURCE,
        resource_label=_resource_label(resource, interaction_locale),
    )


def _resource_to_review_kind(resource: str) -> str:
    return {
        "entity": "entities",
        "relationship": "relationships",
        "system": "systems",
    }.get(resource, "entities")


_RELATIONSHIP_METADATA_FIELDS = {
    "source_id",
    "target_id",
    "source_name",
    "target_name",
    "source_entity_type",
    "target_entity_type",
    "attributes",
}


def _build_field_deltas(
    kind: str,
    delta: dict[str, Any],
    target_id: int | None,
    target_resource: str,
    snapshot: ScopeSnapshot,
    interaction_locale: str,
) -> list[dict[str, Any]]:
    deltas: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    if target_id and target_resource == "entity":
        entity = snapshot.entities_by_id.get(target_id)
        if entity:
            current = {
                "name": entity.name,
                "entity_type": entity.entity_type,
                "description": entity.description or "",
                "aliases": ", ".join(entity.aliases) if entity.aliases else "",
            }
    elif target_id and target_resource == "relationship":
        for relationship in snapshot.relationships:
            if relationship.id == target_id:
                current = {
                    "label": relationship.label,
                    "description": relationship.description or "",
                    "visibility": relationship.visibility,
                }
                break
    elif target_id and target_resource == "system":
        for system in snapshot.systems:
            if system.id == target_id:
                current = {
                    "name": system.name,
                    "description": system.description or "",
                    "constraints": "; ".join(
                        str(value) for value in (system.constraints or [])
                    ),
                }
                break

    for field_key, value in delta.items():
        if value is None or field_key in _RELATIONSHIP_METADATA_FIELDS:
            continue
        field_text_key = _FIELD_TEXT_KEYS.get(field_key)
        label = (
            _suggestion_text(interaction_locale, field_text_key)
            if field_text_key is not None
            else field_key
        )
        before = current.get(field_key)
        after = (
            ", ".join(value) if isinstance(value, list) else str(value) if value else ""
        )
        if isinstance(before, list):
            before = ", ".join(str(item) for item in before)
        deltas.append(
            {
                "field": field_key,
                "label": label,
                "before": str(before) if before else None,
                "after": after,
            }
        )

    for attr in delta.get("attributes", []):
        key = attr.get("key", "")
        surface = attr.get("surface", "")
        if key and surface:
            existing_attrs = snapshot.attributes_by_entity.get(target_id or 0, [])
            existing = next((item for item in existing_attrs if item.key == key), None)
            deltas.append(
                {
                    "field": f"attribute:{key}",
                    "label": _suggestion_text(
                        interaction_locale,
                        CopilotTextKey.TEXT_ATTRIBUTE_FIELD_LABEL,
                        key=key,
                    ),
                    "before": existing.surface if existing else None,
                    "after": surface,
                }
            )
    return deltas


def _serialize_compiled(suggestion: CompiledSuggestion) -> dict[str, Any]:
    return {
        "suggestion_id": suggestion.suggestion_id,
        "kind": suggestion.kind,
        "title": suggestion.title,
        "summary": suggestion.summary,
        "evidence_ids": suggestion.evidence_ids,
        "target": suggestion.target,
        "preview": suggestion.preview,
        "apply": suggestion.apply_action,
        "status": suggestion.status,
    }


def serialize_compiled_suggestions(
    suggestions: list[CompiledSuggestion],
) -> list[dict[str, Any]]:
    return [_serialize_compiled(suggestion) for suggestion in suggestions]


def dismiss_suggestions(
    db: Session, run: CopilotRun, suggestion_ids: list[str]
) -> None:
    """Mark suggestions as dismissed (no world-model mutation)."""
    from sqlalchemy.orm.attributes import flag_modified

    suggestions_by_id = {
        suggestion["suggestion_id"]: suggestion
        for suggestion in (run.suggestions_json or [])
    }
    changed = False
    for suggestion_id in suggestion_ids:
        suggestion = suggestions_by_id.get(suggestion_id)
        if suggestion and suggestion.get("status") == "pending":
            suggestion["status"] = "dismissed"
            changed = True
    if changed:
        flag_modified(run, "suggestions_json")
        db.commit()
