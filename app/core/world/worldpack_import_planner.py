# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Pure reconciliation planning helpers for worldpack import flows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.world.write import (
    WORLDPACK_ORIGIN,
    build_relationship_signature,
    is_worldpack_controlled_by_pack,
    is_worldpack_origin,
)
from app.schemas import (
    WorldpackV1Attribute,
    WorldpackV1Entity,
    WorldpackV1Relationship,
    WorldpackV1System,
)


@dataclass(slots=True)
class PlannedImportWarning:
    code: str
    message: str
    message_key: str
    message_params: dict[str, str | int | float | bool | None] = field(default_factory=dict)
    path: str | None = None


@dataclass(slots=True)
class ImportDecision:
    action: str
    payload: dict[str, Any] = field(default_factory=dict)
    warnings: list[PlannedImportWarning] = field(default_factory=list)
    track_desired_item: bool = True
    preserved_item: str | None = None


class _EntityRow(Protocol):
    name: str
    entity_type: str
    description: str | None
    aliases: list[str] | None
    origin: str
    status: str
    worldpack_pack_id: str | None
    worldpack_key: str | None


class _AttributeRow(Protocol):
    key: str
    surface: str
    truth: str | None
    visibility: str
    sort_order: int
    origin: str
    worldpack_pack_id: str | None


class _RelationshipRow(Protocol):
    label: str
    description: str | None
    visibility: str
    origin: str
    status: str
    worldpack_pack_id: str | None


class _SystemRow(Protocol):
    name: str
    display_type: str
    description: str | None
    data: dict | None
    constraints: list[str] | None
    visibility: str
    origin: str
    status: str
    worldpack_pack_id: str | None


def _warning(
    *,
    code: str,
    message: str,
    message_key: str,
    path: str | None = None,
    message_params: dict[str, str | int | float | bool | None] | None = None,
) -> PlannedImportWarning:
    return PlannedImportWarning(
        code=code,
        message=message,
        message_key=message_key,
        message_params=message_params or {},
        path=path,
    )


def _format_sample(items: list[str], *, max_items: int = 6) -> str:
    sample = items[:max_items]
    rest = len(items) - len(sample)
    if rest > 0:
        return f"{', '.join(sample)} (+{rest} more)"
    return ", ".join(sample)


def collect_ambiguous_alias_warnings(entities: list[WorldpackV1Entity]) -> list[PlannedImportWarning]:
    alias_to_keys: dict[str, set[str]] = {}
    for entity in entities:
        for raw_alias in entity.aliases or []:
            alias = (raw_alias or "").strip()
            if not alias:
                continue
            alias_to_keys.setdefault(alias, set()).add(entity.key)

    warnings: list[PlannedImportWarning] = []
    for alias, keys in sorted(alias_to_keys.items()):
        if len(keys) > 1:
            warnings.append(
                _warning(
                    code="ambiguous_alias",
                    message=f"Alias '{alias}' maps to multiple entities: {sorted(keys)}",
                    message_key="worldpack.import.warning.ambiguous_alias",
                    message_params={"alias": alias, "entity_keys": ", ".join(sorted(keys))},
                    path="entities[*].aliases",
                )
            )
    return warnings


def plan_entity_import(
    existing_entity: _EntityRow | None,
    linked_entity: _EntityRow | None,
    incoming_entity: WorldpackV1Entity,
    *,
    pack_id: str,
    path: str,
) -> ImportDecision:
    name = (incoming_entity.name or "").strip()
    if not name:
        if existing_entity is None:
            return ImportDecision(
                action="skip",
                warnings=[
                    _warning(
                        code="missing_name",
                        message=f"Entity '{incoming_entity.key}' missing name; skipped",
                        message_key="worldpack.import.warning.entity_missing_name",
                        message_params={"key": incoming_entity.key},
                        path=path,
                    )
                ],
                track_desired_item=False,
            )
        return ImportDecision(
            action="keep_existing",
            warnings=[
                _warning(
                    code="missing_name_preserve_existing",
                    message=(
                        f"Entity '{incoming_entity.key}' missing name; kept existing row "
                        "for relationship resolution"
                    ),
                    message_key="worldpack.import.warning.entity_missing_name_preserve_existing",
                    message_params={"key": incoming_entity.key},
                    path=path,
                )
            ],
        )

    desired_values = {
        "name": name,
        "entity_type": incoming_entity.entity_type,
        "description": incoming_entity.description or "",
        "aliases": incoming_entity.aliases or [],
        "status": "confirmed",
        "worldpack_pack_id": pack_id,
        "worldpack_key": incoming_entity.key,
    }

    if existing_entity is None:
        if linked_entity is None:
            return ImportDecision(action="create", payload=desired_values)
        if (
            linked_entity.worldpack_pack_id
            and linked_entity.worldpack_pack_id != pack_id
            or linked_entity.worldpack_key
            and linked_entity.worldpack_key != incoming_entity.key
        ):
            return ImportDecision(
                action="skip",
                warnings=[
                    _warning(
                        code="entity_name_conflict",
                        message=(
                            f"Entity name '{name}' already exists and is linked to a "
                            "different worldpack identity; skipped"
                        ),
                        message_key="worldpack.import.warning.entity_name_conflict",
                        message_params={"name": name},
                        path=path,
                    )
                ],
            )

        changes: dict[str, Any] = {}
        if linked_entity.worldpack_pack_id != pack_id:
            changes["worldpack_pack_id"] = pack_id
        if linked_entity.worldpack_key != incoming_entity.key:
            changes["worldpack_key"] = incoming_entity.key
        return ImportDecision(
            action="link_existing",
            payload=changes,
            warnings=[
                _warning(
                    code="entity_linked_by_name",
                    message=f"Entity '{incoming_entity.key}' linked to existing row by name '{name}'",
                    message_key="worldpack.import.warning.entity_linked_by_name",
                    message_params={"key": incoming_entity.key, "name": name},
                    path=path.removesuffix(".name"),
                )
            ],
        )

    if is_worldpack_origin(existing_entity):
        changes = {
            key: value
            for key, value in desired_values.items()
            if getattr(existing_entity, key) != value
        }
        if changes:
            return ImportDecision(action="update", payload=changes)
        return ImportDecision(action="noop")

    would_change = (
        existing_entity.name != desired_values["name"]
        or existing_entity.entity_type != desired_values["entity_type"]
        or (existing_entity.description or "") != desired_values["description"]
        or (existing_entity.aliases or []) != desired_values["aliases"]
        or existing_entity.status != desired_values["status"]
    )
    return ImportDecision(
        action="preserve",
        preserved_item=incoming_entity.key if would_change else None,
    )


def plan_attribute_import(
    existing_attribute: _AttributeRow | None,
    incoming_attribute: WorldpackV1Attribute,
    *,
    attribute_index: int,
    pack_id: str,
) -> ImportDecision:
    desired_values = {
        "key": incoming_attribute.key,
        "surface": incoming_attribute.surface,
        "truth": incoming_attribute.truth,
        "visibility": incoming_attribute.visibility,
        "sort_order": attribute_index,
        "worldpack_pack_id": pack_id,
    }
    if existing_attribute is None:
        create_payload = dict(desired_values)
        create_payload["origin"] = WORLDPACK_ORIGIN
        return ImportDecision(action="create", payload=create_payload)

    if not is_worldpack_origin(existing_attribute):
        would_change = (
            existing_attribute.surface != desired_values["surface"]
            or (existing_attribute.truth or None) != desired_values["truth"]
            or existing_attribute.visibility != desired_values["visibility"]
            or existing_attribute.sort_order != desired_values["sort_order"]
        )
        return ImportDecision(
            action="preserve",
            preserved_item=incoming_attribute.key if would_change else None,
        )

    changes = {
        key: value
        for key, value in desired_values.items()
        if getattr(existing_attribute, key) != value
    }
    if changes:
        return ImportDecision(action="update", payload=changes)
    return ImportDecision(action="noop")


def plan_relationship_import(
    existing_relationship: _RelationshipRow | None,
    incoming_relationship: WorldpackV1Relationship,
    *,
    pack_id: str,
    source_id: int | None,
    target_id: int | None,
) -> ImportDecision:
    label = (incoming_relationship.label or "").strip()
    if not label:
        return ImportDecision(
            action="skip",
            warnings=[
                _warning(
                    code="missing_relationship_label",
                    message="Relationship missing label; skipped",
                    message_key="worldpack.import.warning.relationship_missing_label",
                )
            ],
            track_desired_item=False,
        )

    if source_id is None or target_id is None:
        return ImportDecision(
            action="skip",
            warnings=[
                _warning(
                    code="missing_relationship_refs",
                    message=(
                        "Relationship refs missing: "
                        f"source_key='{incoming_relationship.source_key}', "
                        f"target_key='{incoming_relationship.target_key}'"
                    ),
                    message_key="worldpack.import.warning.relationship_missing_refs",
                    message_params={
                        "source_key": incoming_relationship.source_key,
                        "target_key": incoming_relationship.target_key,
                    },
                )
            ],
            track_desired_item=False,
        )

    desired_values = {
        "source_id": source_id,
        "target_id": target_id,
        "label": label,
        "description": incoming_relationship.description or "",
        "visibility": incoming_relationship.visibility,
        "status": "confirmed",
        "worldpack_pack_id": pack_id,
        "signature": build_relationship_signature(source_id=source_id, target_id=target_id, label=label),
    }
    if existing_relationship is None:
        create_payload = dict(desired_values)
        create_payload["origin"] = WORLDPACK_ORIGIN
        return ImportDecision(action="create", payload=create_payload)

    if not is_worldpack_controlled_by_pack(existing_relationship, pack_id=pack_id):
        would_change = (
            existing_relationship.label != desired_values["label"]
            or (existing_relationship.description or "") != desired_values["description"]
            or existing_relationship.visibility != desired_values["visibility"]
            or existing_relationship.status != desired_values["status"]
        )
        preserved_item = None
        if would_change:
            preserved_item = (
                f"{incoming_relationship.source_key} --{label}--> {incoming_relationship.target_key}"
            )
        return ImportDecision(
            action="preserve",
            payload={"signature": desired_values["signature"]},
            preserved_item=preserved_item,
        )

    changes = {
        key: value
        for key, value in desired_values.items()
        if key != "signature" and getattr(existing_relationship, key) != value
    }
    if changes:
        return ImportDecision(action="update", payload={**changes, "signature": desired_values["signature"]})
    return ImportDecision(action="noop", payload={"signature": desired_values["signature"]})


def plan_system_import(
    existing_system: _SystemRow | None,
    incoming_system: WorldpackV1System,
    *,
    pack_id: str,
    path: str,
) -> ImportDecision:
    name = (incoming_system.name or "").strip()
    if not name:
        return ImportDecision(
            action="skip",
            warnings=[
                _warning(
                    code="missing_name",
                    message="System missing name; skipped",
                    message_key="worldpack.import.warning.system_missing_name",
                    path=path,
                )
            ],
            track_desired_item=False,
        )

    desired_values = {
        "name": name,
        "display_type": incoming_system.display_type,
        "description": incoming_system.description or "",
        "data": incoming_system.data or {},
        "constraints": incoming_system.constraints or [],
        "visibility": incoming_system.visibility,
        "status": "confirmed",
        "worldpack_pack_id": pack_id,
    }
    if existing_system is None:
        create_payload = dict(desired_values)
        create_payload["origin"] = WORLDPACK_ORIGIN
        return ImportDecision(action="create", payload=create_payload)

    if not is_worldpack_origin(existing_system):
        would_change = (
            existing_system.display_type != desired_values["display_type"]
            or (existing_system.description or "") != desired_values["description"]
            or (existing_system.data or {}) != desired_values["data"]
            or (existing_system.constraints or []) != desired_values["constraints"]
            or existing_system.visibility != desired_values["visibility"]
            or existing_system.status != desired_values["status"]
        )
        return ImportDecision(action="preserve", preserved_item=name if would_change else None)

    if existing_system.worldpack_pack_id and existing_system.worldpack_pack_id != pack_id:
        return ImportDecision(
            action="skip",
            warnings=[
                _warning(
                    code="system_name_conflict",
                    message=f"System name '{name}' already exists for a different pack; skipped",
                    message_key="worldpack.import.warning.system_name_conflict",
                    message_params={"name": name},
                    path=path,
                )
            ],
        )

    changes = {
        key: value
        for key, value in desired_values.items()
        if getattr(existing_system, key) != value
    }
    if changes:
        return ImportDecision(action="update", payload=changes)
    return ImportDecision(action="noop")


def plan_entity_deletion(
    worldpack_key: str | None,
    *,
    has_non_pack_attribute_dependency: bool,
    has_non_pack_relationship_dependency: bool,
) -> ImportDecision:
    if has_non_pack_attribute_dependency or has_non_pack_relationship_dependency:
        return ImportDecision(
            action="keep",
            warnings=[
                _warning(
                    code="skip_delete_promoted_entity",
                    message=f"Entity '{worldpack_key}' has non-worldpack dependencies; kept",
                    message_key="worldpack.import.warning.skip_delete_promoted_entity",
                    message_params={"key": worldpack_key},
                    path="entities",
                )
            ],
        )
    return ImportDecision(action="delete")


def build_preserved_entity_warning(entity_keys: set[str]) -> PlannedImportWarning | None:
    if not entity_keys:
        return None
    keys = sorted(entity_keys)
    return _warning(
        code="preserved_entities_skipped",
        message=f"Skipped overwriting {len(keys)} preserved entities: {_format_sample(keys)}",
        message_key="worldpack.import.warning.preserved_entities_skipped",
        message_params={"count": len(keys), "sample": _format_sample(keys)},
        path="entities",
    )


def build_preserved_attribute_warning(attribute_keys_by_entity: dict[str, set[str]]) -> PlannedImportWarning | None:
    if not attribute_keys_by_entity:
        return None

    total = sum(len(values) for values in attribute_keys_by_entity.values())
    sample_entities = sorted(attribute_keys_by_entity.keys())[:3]
    parts: list[str] = []
    for entity_key in sample_entities:
        keys = sorted(attribute_keys_by_entity[entity_key])
        parts.append(f"{entity_key}[{_format_sample(keys, max_items=3)}]")
    rest = len(attribute_keys_by_entity) - len(sample_entities)
    suffix = f" (+{rest} more entities)" if rest > 0 else ""
    return _warning(
        code="preserved_attributes_skipped",
        message=f"Skipped overwriting {total} preserved attributes: {'; '.join(parts)}{suffix}",
        message_key="worldpack.import.warning.preserved_attributes_skipped",
        message_params={"count": total, "sample": '; '.join(parts), "more_entities_count": rest},
        path="entities[*].attributes",
    )


def build_preserved_relationship_warning(relationship_signatures: set[str]) -> PlannedImportWarning | None:
    if not relationship_signatures:
        return None
    signatures = sorted(relationship_signatures)
    return _warning(
        code="preserved_relationships_skipped",
        message=(
            f"Skipped overwriting {len(signatures)} preserved relationships: "
            f"{_format_sample(signatures)}"
        ),
        message_key="worldpack.import.warning.preserved_relationships_skipped",
        message_params={"count": len(signatures), "sample": _format_sample(signatures)},
        path="relationships",
    )


def build_preserved_system_warning(system_names: set[str]) -> PlannedImportWarning | None:
    if not system_names:
        return None
    names = sorted(system_names)
    return _warning(
        code="preserved_systems_skipped",
        message=f"Skipped overwriting {len(names)} preserved systems: {_format_sample(names)}",
        message_key="worldpack.import.warning.preserved_systems_skipped",
        message_params={"count": len(names), "sample": _format_sample(names)},
        path="systems",
    )
