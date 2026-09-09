# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only


"""Pure normalization, shape conversion and merging of extracted world items."""

from __future__ import annotations

import hashlib
from app.core.world.write import normalize_system_data_for_write
from app.schemas import WorldGenerateWarning
from .generation_schema import (
    WorldGenEntity,
    WorldGenRelationship,
    WorldGenSystemItem,
    WorldGenSystem,
    WorldGenLLMOutput,
    WorldGenSystemDisplayType,
    _normalize_worldgen_system_display_type,
)


def _norm(s: str | None) -> str:
    return str(s or "").strip()


def _norm_aliases(*, name: str, aliases: list[str]) -> list[str]:
    base = _norm(name)
    out: list[str] = []
    seen: set[str] = set()
    for a in aliases or []:
        a = _norm(a)
        if not a or a == base:
            continue
        if a in seen:
            continue
        seen.add(a)
        out.append(a)
    return out


def _choose_entity_type(current: str, candidate: str) -> str:
    cur = _norm(current) or "Concept"
    new = _norm(candidate) or "Concept"
    generic = {"concept", "other"}
    if cur.lower() in generic and new.lower() not in generic:
        return new
    return cur


def _prefer_longer_text(current: str, candidate: str) -> str:
    cur = _norm(current)
    new = _norm(candidate)
    return new if len(new) > len(cur) else cur


def _merge_optional_text(current: str | None, candidate: str | None) -> str | None:
    merged = _prefer_longer_text(current or "", candidate or "")
    return merged or None


def _worldgen_warning(
    *,
    code: str,
    message_key: str,
    message: str,
    path: str | None = None,
    message_params: dict[str, str | int | float | bool | None] | None = None,
) -> WorldGenerateWarning:
    return WorldGenerateWarning(
        code=code,
        message=message,
        message_key=message_key,
        message_params=message_params or {},
        path=path,
    )


def _merge_worldgen_system_display_type(
    current: WorldGenSystemDisplayType,
    candidate: WorldGenSystemDisplayType,
) -> WorldGenSystemDisplayType:
    if current == candidate:
        return current
    # Mixed chunk shapes are ambiguous. Downgrade to list so later persistence
    # does not silently discard structure-specific fields like time or nesting.
    return "list"


def _worldgen_system_item_key(
    item: WorldGenSystemItem,
    *,
    display_type: WorldGenSystemDisplayType,
) -> tuple[str, str] | str:
    if display_type == "timeline":
        return (_norm(item.time), item.label)
    return item.label


def _normalize_worldgen_system_item(
    item: WorldGenSystemItem,
) -> WorldGenSystemItem | None:
    label = _norm(item.label)
    if not label:
        return None
    return WorldGenSystemItem(
        label=label,
        description=_norm(item.description) or None,
        time=_norm(item.time) or None,
        children=_merge_worldgen_system_items(
            list(item.children or []), display_type="hierarchy"
        ),
    )


def _merge_worldgen_system_item(
    current: WorldGenSystemItem, candidate: WorldGenSystemItem
) -> WorldGenSystemItem:
    return WorldGenSystemItem(
        label=current.label,
        description=_merge_optional_text(current.description, candidate.description),
        time=_merge_optional_text(current.time, candidate.time),
        children=_merge_worldgen_system_items(
            [*(current.children or []), *(candidate.children or [])],
            display_type="hierarchy",
        ),
    )


def _merge_worldgen_system_items(
    items: list[WorldGenSystemItem],
    *,
    display_type: WorldGenSystemDisplayType,
) -> list[WorldGenSystemItem]:
    merged_items: dict[tuple[str, str] | str, WorldGenSystemItem] = {}
    ordered_keys: list[tuple[str, str] | str] = []
    for raw_item in items:
        item = _normalize_worldgen_system_item(raw_item)
        if item is None:
            continue
        key = _worldgen_system_item_key(item, display_type=display_type)
        existing = merged_items.get(key)
        if existing is None:
            merged_items[key] = item
            ordered_keys.append(key)
            continue
        merged_items[key] = _merge_worldgen_system_item(existing, item)
    return [merged_items[key] for key in ordered_keys]


def _flatten_worldgen_system_items_to_list(
    items: list[WorldGenSystemItem],
    *,
    source_display_type: WorldGenSystemDisplayType,
    path_prefix: tuple[str, ...] = (),
) -> list[WorldGenSystemItem]:
    flat_items: list[WorldGenSystemItem] = []
    for raw_item in items:
        item = _normalize_worldgen_system_item(raw_item)
        if item is None:
            continue

        if source_display_type == "hierarchy":
            path = (*path_prefix, item.label)
            flat_items.append(
                WorldGenSystemItem(
                    label=" / ".join(path),
                    description=item.description,
                )
            )
            flat_items.extend(
                _flatten_worldgen_system_items_to_list(
                    list(item.children or []),
                    source_display_type="hierarchy",
                    path_prefix=path,
                )
            )
            continue

        label = item.label
        if source_display_type == "timeline":
            time = _norm(item.time)
            if time:
                label = f"[{time}] {label}"

        flat_items.append(
            WorldGenSystemItem(
                label=label,
                description=item.description,
            )
        )
    return flat_items


def _make_worldgen_hierarchy_node_id(*, system_name: str, path: tuple[str, ...]) -> str:
    digest = hashlib.sha1(
        "\x1f".join((system_name, *path)).encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()[:12]
    return f"wg_{digest}"


def _build_worldgen_list_data(items: list[WorldGenSystemItem]) -> dict:
    items_payload = []
    for item in items:
        payload = {
            "label": item.label,
            "visibility": "reference",
        }
        description = _norm(item.description)
        if description:
            payload["description"] = description
        items_payload.append(payload)
    return {"items": items_payload} if items_payload else {}


def _build_worldgen_hierarchy_nodes(
    *,
    system_name: str,
    items: list[WorldGenSystemItem],
    path_prefix: tuple[str, ...] = (),
) -> list[dict]:
    nodes: list[dict] = []
    for item in items:
        path = (*path_prefix, item.label)
        node = {
            "id": _make_worldgen_hierarchy_node_id(system_name=system_name, path=path),
            "label": item.label,
            "visibility": "reference",
            "children": _build_worldgen_hierarchy_nodes(
                system_name=system_name,
                items=list(item.children or []),
                path_prefix=path,
            ),
        }
        nodes.append(node)
    return nodes


def _build_worldgen_timeline_data(
    *,
    items: list[WorldGenSystemItem],
    system_index: int,
    warnings: list[WorldGenerateWarning],
) -> dict:
    events = []
    for item_index, item in enumerate(items):
        time = _norm(item.time)
        if not time:
            warnings.append(
                _worldgen_warning(
                    code="system_item_skipped",
                    message_key="world.generate.warning.system_item_missing_time",
                    message="Timeline item missing time; skipped",
                    message_params={"display_type": "timeline"},
                    path=f"systems[{system_index}].items[{item_index}].time",
                )
            )
            continue

        event = {
            "time": time,
            "label": item.label,
            "visibility": "reference",
        }
        description = _norm(item.description)
        if description:
            event["description"] = description
        events.append(event)
    return {"events": events} if events else {}


def _build_worldgen_system_data(
    *,
    system: WorldGenSystem,
    system_index: int,
    warnings: list[WorldGenerateWarning],
) -> tuple[WorldGenSystemDisplayType, dict]:
    display_type = _normalize_worldgen_system_display_type(system.display_type)
    if display_type == "hierarchy":
        raw_data = (
            {
                "nodes": _build_worldgen_hierarchy_nodes(
                    system_name=system.name, items=list(system.items or [])
                )
            }
            if system.items
            else {}
        )
    elif display_type == "timeline":
        raw_data = _build_worldgen_timeline_data(
            items=list(system.items or []),
            system_index=system_index,
            warnings=warnings,
        )
    else:
        raw_data = _build_worldgen_list_data(list(system.items or []))

    return display_type, normalize_system_data_for_write(display_type, raw_data)


def _merge_worldgen_outputs(
    outputs: list[WorldGenLLMOutput],
    *,
    warnings: list[WorldGenerateWarning] | None = None,
) -> WorldGenLLMOutput:
    entities: dict[str, WorldGenEntity] = {}
    relationships: dict[tuple[str, str, str], WorldGenRelationship] = {}
    systems: dict[str, WorldGenSystem] = {}
    warned_system_display_type_conflicts: set[str] = set()

    for output in outputs:
        for ent in output.entities or []:
            name = _norm(ent.name)
            if not name:
                continue
            existing = entities.get(name)
            aliases = _norm_aliases(name=name, aliases=list(ent.aliases or []))
            if existing is None:
                entities[name] = WorldGenEntity(
                    name=name,
                    entity_type=_norm(ent.entity_type) or "Concept",
                    description=_norm(ent.description),
                    aliases=aliases,
                )
                continue

            merged_aliases = _norm_aliases(
                name=name, aliases=[*existing.aliases, *aliases]
            )
            entities[name] = WorldGenEntity(
                name=name,
                entity_type=_choose_entity_type(existing.entity_type, ent.entity_type),
                description=_prefer_longer_text(existing.description, ent.description),
                aliases=merged_aliases,
            )

        for rel in output.relationships or []:
            source = _norm(rel.source)
            target = _norm(rel.target)
            label = _norm(rel.label)
            if not source or not target or not label:
                continue
            key = (source, target, label)
            existing = relationships.get(key)
            if existing is None:
                relationships[key] = WorldGenRelationship(
                    source=source,
                    target=target,
                    label=label,
                    description=_norm(rel.description),
                )
                continue
            relationships[key] = WorldGenRelationship(
                source=source,
                target=target,
                label=label,
                description=_prefer_longer_text(existing.description, rel.description),
            )

        for sys in output.systems or []:
            name = _norm(sys.name)
            if not name:
                continue
            existing = systems.get(name)
            incoming_display_type = _normalize_worldgen_system_display_type(
                sys.display_type
            )
            incoming_items = _merge_worldgen_system_items(
                list(sys.items or []),
                display_type=incoming_display_type,
            )
            incoming_constraints: list[str] = []
            seen_constraints: set[str] = set()
            for c in sys.constraints or []:
                c = _norm(c)
                if not c or c in seen_constraints:
                    continue
                seen_constraints.add(c)
                incoming_constraints.append(c)

            if existing is None:
                systems[name] = WorldGenSystem(
                    name=name,
                    description=_norm(sys.description),
                    display_type=incoming_display_type,
                    items=incoming_items,
                    constraints=incoming_constraints,
                )
                continue

            existing_display_type = _normalize_worldgen_system_display_type(
                existing.display_type
            )
            merged_display_type = _merge_worldgen_system_display_type(
                existing_display_type,
                incoming_display_type,
            )
            merged_constraints: list[str] = []
            seen_merged_constraints: set[str] = set()
            for c in [*(existing.constraints or []), *incoming_constraints]:
                c = _norm(c)
                if not c or c in seen_merged_constraints:
                    continue
                seen_merged_constraints.add(c)
                merged_constraints.append(c)

            if (
                existing_display_type != incoming_display_type
                and name not in warned_system_display_type_conflicts
            ):
                warned_system_display_type_conflicts.add(name)
                if warnings is not None:
                    warnings.append(
                        _worldgen_warning(
                            code="system_display_type_conflict",
                            message_key="world.generate.warning.system_display_type_conflict",
                            message="System display types conflict across chunks; downgraded to list",
                            message_params={
                                "name": name,
                                "current_display_type": existing_display_type,
                                "incoming_display_type": incoming_display_type,
                                "downgraded_display_type": "list",
                            },
                            path=f"systems[{name}].display_type",
                        )
                    )

            if existing_display_type != incoming_display_type:
                merged_items = _merge_worldgen_system_items(
                    [
                        *_flatten_worldgen_system_items_to_list(
                            list(existing.items or []),
                            source_display_type=existing_display_type,
                        ),
                        *_flatten_worldgen_system_items_to_list(
                            incoming_items,
                            source_display_type=incoming_display_type,
                        ),
                    ],
                    display_type="list",
                )
            else:
                merged_items = _merge_worldgen_system_items(
                    [*(existing.items or []), *incoming_items],
                    display_type=merged_display_type,
                )

            systems[name] = WorldGenSystem(
                name=name,
                description=_prefer_longer_text(existing.description, sys.description),
                display_type=merged_display_type,
                items=merged_items,
                constraints=merged_constraints,
            )

    return WorldGenLLMOutput(
        entities=list(entities.values()),
        relationships=list(relationships.values()),
        systems=list(systems.values()),
    )
