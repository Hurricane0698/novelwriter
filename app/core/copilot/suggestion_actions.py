# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Target resolution and apply-action helpers for copilot suggestions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.core.copilot.messages import CopilotTextKey
from app.core.copilot.scope import ScopeSnapshot
from app.language_policy import get_language_policy

SuggestionTextFn = Callable[..., str]


@dataclass(frozen=True)
class EntitySuggestionCandidate:
    suggestion_id: str
    name: str
    entity_type: str


def _normalize_entity_name_key(
    name: str | None,
    *,
    language: str | None,
) -> str:
    text = (name or "").strip()
    if not text:
        return ""
    return get_language_policy(language, sample_text=text).normalize_for_matching(text)


def _find_existing_entity_ref_by_name_or_alias(
    name: str | None,
    snapshot: ScopeSnapshot,
) -> dict[str, Any] | None:
    key = _normalize_entity_name_key(name, language=snapshot.novel_language)
    if not key:
        return None

    refs = list(snapshot.novel_entity_refs_by_name_key.get(key, ()))
    if len(refs) == 1:
        ref = refs[0]
        entity = snapshot.entities_by_id.get(ref.entity_id)
        return {
            "entity_id": ref.entity_id,
            "name": entity.name if entity is not None else ref.name,
            "status": entity.status if entity is not None else ref.status,
            "entity": entity,
        }
    if len(refs) > 1:
        return None

    matches: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for entity in snapshot.entities:
        candidate_keys = [
            _normalize_entity_name_key(entity.name, language=snapshot.novel_language)
        ]
        candidate_keys.extend(
            _normalize_entity_name_key(alias, language=snapshot.novel_language)
            for alias in (entity.aliases or [])
        )
        if key not in candidate_keys or entity.id in seen_ids:
            continue
        seen_ids.add(entity.id)
        matches.append(
            {
                "entity_id": entity.id,
                "name": entity.name,
                "status": entity.status,
                "entity": entity,
            }
        )
    return matches[0] if len(matches) == 1 else None


def _system_name_exists(
    name: str | None,
    snapshot: ScopeSnapshot,
) -> bool:
    key = _normalize_entity_name_key(name, language=snapshot.novel_language)
    if not key:
        return False
    if snapshot.novel_system_refs_by_name_key.get(key):
        return True
    return any(
        _normalize_entity_name_key(system.name, language=snapshot.novel_language) == key
        for system in snapshot.systems
    )


def build_entity_suggestion_candidates(
    raw_suggestions: list[dict[str, Any]],
    suggestion_ids: list[str],
    *,
    language: str | None,
) -> dict[str, EntitySuggestionCandidate]:
    candidates: dict[str, EntitySuggestionCandidate] = {}
    for raw, suggestion_id in zip(raw_suggestions, suggestion_ids):
        if raw.get("kind") != "create_entity":
            continue
        delta = raw.get("delta") or {}
        name = str(delta.get("name") or "").strip()
        key = _normalize_entity_name_key(name, language=language)
        if not key:
            continue
        candidates[key] = EntitySuggestionCandidate(
            suggestion_id=suggestion_id,
            name=name,
            entity_type=str(delta.get("entity_type", "Other")),
        )
    return candidates


def expand_relationship_entity_dependencies(
    raw_suggestions: list[dict[str, Any]],
    snapshot: ScopeSnapshot,
    interaction_locale: str,
    *,
    suggestion_text: SuggestionTextFn,
) -> list[dict[str, Any]]:
    """Synthesize missing create_entity suggestions for relationship endpoints."""
    expanded: list[dict[str, Any]] = []
    known_candidate_keys = {
        _normalize_entity_name_key(
            str((raw.get("delta") or {}).get("name") or ""),
            language=snapshot.novel_language,
        )
        for raw in raw_suggestions
        if raw.get("kind") == "create_entity"
    }
    synthesized_keys: set[str] = set()

    for raw in raw_suggestions:
        if (
            raw.get("kind") == "create_relationship"
            and raw.get("target_resource", "relationship") == "relationship"
        ):
            delta = raw.get("delta") or {}
            for endpoint in ("source", "target"):
                endpoint_id = delta.get(f"{endpoint}_id")
                if (
                    isinstance(endpoint_id, int)
                    and endpoint_id in snapshot.entities_by_id
                ):
                    continue

                endpoint_name = str(delta.get(f"{endpoint}_name") or "").strip()
                key = _normalize_entity_name_key(
                    endpoint_name,
                    language=snapshot.novel_language,
                )
                if not key:
                    continue
                if key in known_candidate_keys or key in synthesized_keys:
                    continue
                if (
                    _find_existing_entity_ref_by_name_or_alias(endpoint_name, snapshot)
                    is not None
                ):
                    continue

                endpoint_type = (
                    str(delta.get(f"{endpoint}_entity_type") or "Other").strip()
                    or "Other"
                )
                expanded.append(
                    {
                        "kind": "create_entity",
                        "title": suggestion_text(
                            interaction_locale,
                            CopilotTextKey.SUGGESTION_SYNTH_ENTITY_TITLE,
                            entity_name=endpoint_name,
                        ),
                        "summary": suggestion_text(
                            interaction_locale,
                            CopilotTextKey.SUGGESTION_SYNTH_ENTITY_SUMMARY,
                            entity_name=endpoint_name,
                        ),
                        "target_resource": "entity",
                        "target_id": None,
                        "cited_evidence_indices": list(
                            raw.get("cited_evidence_indices") or []
                        ),
                        "delta": {
                            "name": endpoint_name,
                            "entity_type": endpoint_type,
                        },
                    }
                )
                synthesized_keys.add(key)
                known_candidate_keys.add(key)

        expanded.append(raw)

    return expanded


def resolve_target(
    resource: str,
    target_id: int | None,
    snapshot: ScopeSnapshot,
) -> dict[str, Any] | None:
    if target_id is None:
        return None
    if resource == "entity":
        entity = snapshot.entities_by_id.get(target_id)
        if entity:
            return {
                "id": entity.id,
                "label": entity.name,
                "is_draft": entity.status == "draft",
            }
    elif resource == "relationship":
        for relationship in snapshot.relationships:
            if relationship.id == target_id:
                source = snapshot.entities_by_id.get(relationship.source_id)
                target = snapshot.entities_by_id.get(relationship.target_id)
                label = f"{source.name if source else '?'} ↔ {target.name if target else '?'}"
                return {
                    "id": relationship.id,
                    "label": label,
                    "is_draft": relationship.status == "draft",
                }
    elif resource == "system":
        for system in snapshot.systems:
            if system.id == target_id:
                return {
                    "id": system.id,
                    "label": system.name,
                    "is_draft": system.status == "draft",
                }
    return None


_ENTITY_UPDATE_FIELDS = {"name", "entity_type", "description", "aliases"}
_RELATIONSHIP_UPDATE_FIELDS = {"label", "description", "visibility"}
_SYSTEM_UPDATE_FIELDS = {"name", "description", "constraints", "display_type"}
_DRAFT_ENTITY_UPDATE_FIELDS = {"name", "entity_type", "description", "aliases"}
_DRAFT_REL_UPDATE_FIELDS = {"label", "description", "visibility"}
_DRAFT_SYSTEM_UPDATE_FIELDS = {"name", "description", "constraints"}


def build_update_action(
    kind: str,
    delta: dict[str, Any],
    target_resource: str,
    target_id: int,
    snapshot: ScopeSnapshot,
    mode: str,
) -> dict[str, Any] | None:
    is_draft_governance = (
        snapshot.profile == "draft_governance" or mode == "draft_cleanup"
    )
    if target_resource == "entity":
        allowed = (
            _DRAFT_ENTITY_UPDATE_FIELDS
            if is_draft_governance
            else _ENTITY_UPDATE_FIELDS
        )
        data = {k: v for k, v in delta.items() if k in allowed and v is not None}
        attr_actions = _compile_attribute_actions(
            delta.get("attributes", []), target_id, snapshot
        )
        if not data and not attr_actions:
            return None
        action: dict[str, Any] = {
            "type": "update_entity",
            "entity_id": target_id,
            "data": data,
        }
        if attr_actions:
            action["attribute_actions"] = attr_actions
        return action

    if target_resource == "relationship":
        allowed = (
            _DRAFT_REL_UPDATE_FIELDS
            if is_draft_governance
            else _RELATIONSHIP_UPDATE_FIELDS
        )
        data = {k: v for k, v in delta.items() if k in allowed and v is not None}
        return (
            {"type": "update_relationship", "relationship_id": target_id, "data": data}
            if data
            else None
        )

    if target_resource == "system":
        allowed = (
            _DRAFT_SYSTEM_UPDATE_FIELDS
            if is_draft_governance
            else _SYSTEM_UPDATE_FIELDS
        )
        data = {k: v for k, v in delta.items() if k in allowed and v is not None}
        return (
            {"type": "update_system", "system_id": target_id, "data": data}
            if data
            else None
        )

    return None


def _compile_attribute_actions(
    raw_attrs: list[dict[str, Any]],
    entity_id: int,
    snapshot: ScopeSnapshot,
) -> list[dict[str, Any]]:
    if not raw_attrs:
        return []
    existing_attrs = snapshot.attributes_by_entity.get(entity_id, [])
    existing_by_key = {attr.key: attr for attr in existing_attrs}
    actions: list[dict[str, Any]] = []
    for raw_attr in raw_attrs:
        key = raw_attr.get("key")
        surface = raw_attr.get("surface")
        if not key or not surface:
            continue
        if key in existing_by_key:
            attr = existing_by_key[key]
            if attr.surface != surface:
                actions.append(
                    {
                        "type": "update_attribute",
                        "entity_id": entity_id,
                        "attribute_id": attr.id,
                        "data": {"surface": surface},
                    }
                )
        else:
            actions.append(
                {
                    "type": "create_attribute",
                    "entity_id": entity_id,
                    "data": {"key": key, "surface": surface},
                }
            )
    return actions


def _resolve_relationship_endpoint_reference(
    *,
    endpoint_id: Any,
    endpoint_name: Any,
    snapshot: ScopeSnapshot,
    entity_candidates: dict[str, EntitySuggestionCandidate],
) -> dict[str, Any] | None:
    if isinstance(endpoint_id, int) and endpoint_id in snapshot.entities_by_id:
        entity = snapshot.entities_by_id[endpoint_id]
        return {"kind": "existing", "entity_id": entity.id, "label": entity.name}

    name = str(endpoint_name or "").strip()
    if not name:
        return None

    existing_entity = _find_existing_entity_ref_by_name_or_alias(name, snapshot)
    if existing_entity is not None:
        return {
            "kind": "existing",
            "entity_id": existing_entity["entity_id"],
            "label": existing_entity["name"],
        }

    candidate = entity_candidates.get(
        _normalize_entity_name_key(name, language=snapshot.novel_language)
    )
    if candidate is not None:
        return {
            "kind": "suggestion",
            "suggestion_id": candidate.suggestion_id,
            "entity_name": candidate.name,
        }
    return None


def build_create_action(
    kind: str,
    delta: dict[str, Any],
    target_resource: str,
    snapshot: ScopeSnapshot,
    entity_candidates: dict[str, EntitySuggestionCandidate],
) -> dict[str, Any] | None:
    if target_resource == "entity":
        name = delta.get("name")
        if not name:
            return None
        if _find_existing_entity_ref_by_name_or_alias(name, snapshot) is not None:
            return None
        data: dict[str, Any] = {
            "name": name,
            "entity_type": delta.get("entity_type", "Other"),
        }
        if delta.get("description"):
            data["description"] = delta["description"]
        if delta.get("aliases"):
            data["aliases"] = delta["aliases"]
        action: dict[str, Any] = {"type": "create_entity", "data": data}
        attrs = delta.get("attributes", [])
        if attrs:
            action["deferred_attribute_actions"] = [
                {
                    "type": "create_attribute",
                    "data": {"key": attr["key"], "surface": attr["surface"]},
                }
                for attr in attrs
                if attr.get("key") and attr.get("surface")
            ]
        return action

    if target_resource == "relationship":
        source_id = delta.get("source_id")
        target_id = delta.get("target_id")
        source_name = delta.get("source_name")
        target_name = delta.get("target_name")
        label = delta.get("label")
        if not label:
            return None
        source_ref = _resolve_relationship_endpoint_reference(
            endpoint_id=source_id,
            endpoint_name=source_name,
            snapshot=snapshot,
            entity_candidates=entity_candidates,
        )
        target_ref = _resolve_relationship_endpoint_reference(
            endpoint_id=target_id,
            endpoint_name=target_name,
            snapshot=snapshot,
            entity_candidates=entity_candidates,
        )
        if source_ref is None or target_ref is None:
            return None
        data = {"label": label}
        if delta.get("description"):
            data["description"] = delta["description"]
        if source_ref["kind"] == "existing":
            data["source_id"] = source_ref["entity_id"]
        if target_ref["kind"] == "existing":
            data["target_id"] = target_ref["entity_id"]
        action: dict[str, Any] = {"type": "create_relationship", "data": data}
        if source_ref["kind"] != "existing" or target_ref["kind"] != "existing":
            action["endpoint_dependencies"] = {
                "source": source_ref,
                "target": target_ref,
            }
        return action

    if target_resource == "system":
        name = delta.get("name")
        if not name:
            return None
        if _system_name_exists(name, snapshot):
            return None
        data = {"name": name, "display_type": delta.get("display_type", "list")}
        if delta.get("description"):
            data["description"] = delta["description"]
        if delta.get("constraints"):
            data["constraints"] = delta["constraints"]
        return {"type": "create_system", "data": data}

    return None


def build_non_actionable_create_reason(
    kind: str,
    delta: dict[str, Any],
    target_resource: str,
    snapshot: ScopeSnapshot,
    entity_candidates: dict[str, EntitySuggestionCandidate],
    interaction_locale: str,
    *,
    suggestion_text: SuggestionTextFn,
) -> str:
    if target_resource == "entity":
        if not delta.get("name"):
            return suggestion_text(
                interaction_locale,
                CopilotTextKey.SUGGESTION_CREATE_REASON_ENTITY_INCOMPLETE,
            )
        return suggestion_text(
            interaction_locale,
            CopilotTextKey.SUGGESTION_CREATE_REASON_ENTITY_NAME_COLLISION,
        )

    if target_resource == "relationship":
        source_id = delta.get("source_id")
        target_id = delta.get("target_id")
        source_name = str(delta.get("source_name") or "").strip()
        target_name = str(delta.get("target_name") or "").strip()
        label = delta.get("label")
        if not label:
            return suggestion_text(
                interaction_locale,
                CopilotTextKey.SUGGESTION_CREATE_REASON_RELATIONSHIP_INCOMPLETE,
            )
        if not any([isinstance(source_id, int), source_name]) or not any(
            [isinstance(target_id, int), target_name]
        ):
            return suggestion_text(
                interaction_locale,
                CopilotTextKey.SUGGESTION_CREATE_REASON_RELATIONSHIP_INCOMPLETE,
            )

        source_ref = _resolve_relationship_endpoint_reference(
            endpoint_id=source_id,
            endpoint_name=source_name,
            snapshot=snapshot,
            entity_candidates=entity_candidates,
        )
        target_ref = _resolve_relationship_endpoint_reference(
            endpoint_id=target_id,
            endpoint_name=target_name,
            snapshot=snapshot,
            entity_candidates=entity_candidates,
        )
        if source_ref is None or target_ref is None:
            return suggestion_text(
                interaction_locale,
                CopilotTextKey.SUGGESTION_CREATE_REASON_RELATIONSHIP_DEPENDENCY,
            )
        return suggestion_text(
            interaction_locale,
            CopilotTextKey.SUGGESTION_CREATE_REASON_RELATIONSHIP_CONFLICT,
        )

    if target_resource == "system":
        if not delta.get("name"):
            return suggestion_text(
                interaction_locale,
                CopilotTextKey.SUGGESTION_CREATE_REASON_SYSTEM_INCOMPLETE,
            )
        return suggestion_text(
            interaction_locale,
            CopilotTextKey.SUGGESTION_CREATE_REASON_SYSTEM_NAME_COLLISION,
        )

    return suggestion_text(
        interaction_locale,
        CopilotTextKey.SUGGESTION_REASON_CANNOT_APPLY_DIRECT,
    )
