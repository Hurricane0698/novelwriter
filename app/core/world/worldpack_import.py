# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Worldpack import application service shared by API and background flows."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.world.write import (
    WORLDPACK_ORIGIN,
    build_relationship_signature,
    relationship_signature_from_row,
)
from app.core.world.worldpack_import_planner import (
    PlannedImportWarning,
    build_preserved_attribute_warning,
    build_preserved_entity_warning,
    build_preserved_relationship_warning,
    build_preserved_system_warning,
    collect_ambiguous_alias_warnings,
    plan_attribute_import,
    plan_entity_deletion,
    plan_entity_import,
    plan_relationship_import,
    plan_system_import,
)
from app.models import (
    Novel,
    WorldEntity,
    WorldEntityAttribute,
    WorldRelationship,
    WorldSystem,
)
from app.schemas import WorldpackV1Payload

_WORLDPACK_SCHEMA_VERSION = "worldpack.v1"


class WorldpackImportError(RuntimeError):
    code = "worldpack_import_failed"
    message = "Worldpack import failed"

    def __str__(self) -> str:
        return self.message


class WorldpackNovelNotFoundError(WorldpackImportError):
    code = "novel_not_found"
    message = "Novel not found"


class UnsupportedWorldpackSchemaVersionError(WorldpackImportError):
    code = "worldpack_unsupported_schema_version"
    message = "Unsupported schema_version"


class WorldpackImportConflictError(WorldpackImportError):
    code = "worldpack_import_conflict"
    message = "Worldpack import conflict"


@dataclass(slots=True)
class WorldpackImportCountsResult:
    entities_created: int = 0
    entities_updated: int = 0
    entities_deleted: int = 0
    attributes_created: int = 0
    attributes_updated: int = 0
    attributes_deleted: int = 0
    relationships_created: int = 0
    relationships_updated: int = 0
    relationships_deleted: int = 0
    systems_created: int = 0
    systems_updated: int = 0
    systems_deleted: int = 0


@dataclass(slots=True)
class WorldpackImportWarningResult:
    code: str
    message: str
    message_key: str
    message_params: dict[str, str | int | float | bool | None] = field(default_factory=dict)
    path: str | None = None


@dataclass(slots=True)
class WorldpackImportResult:
    pack_id: str
    counts: WorldpackImportCountsResult
    warnings: list[WorldpackImportWarningResult] = field(default_factory=list)


def _ensure_novel_exists(novel_id: int, db: Session) -> None:
    novel = db.query(Novel.id).filter(Novel.id == novel_id).first()
    if novel is None:
        raise WorldpackNovelNotFoundError()


def _append_warning(
    warnings: list[WorldpackImportWarningResult],
    warning: PlannedImportWarning,
    *,
    fallback_path: str | None = None,
) -> None:
    warnings.append(
        WorldpackImportWarningResult(
            code=warning.code,
            message=warning.message,
            message_key=warning.message_key,
            message_params=dict(warning.message_params),
            path=warning.path if warning.path is not None else fallback_path,
        )
    )


def _sync_entities_and_attributes(
    *,
    novel_id: int,
    body: WorldpackV1Payload,
    pack_id: str,
    db: Session,
    counts: WorldpackImportCountsResult,
    warnings: list[WorldpackImportWarningResult],
) -> tuple[dict[str, WorldEntity], set[str], set[str], dict[str, set[str]]]:
    seen_entity_keys: set[str] = set()
    entities_by_key: dict[str, WorldEntity] = {}
    desired_entity_keys: set[str] = set()
    preserved_entity_keys: set[str] = set()
    preserved_attr_keys_by_entity: dict[str, set[str]] = {}

    for idx, entity_in in enumerate(body.entities):
        if entity_in.key in seen_entity_keys:
            warnings.append(
                WorldpackImportWarningResult(
                    code="duplicate_entity_key",
                    message=f"Duplicate entity key '{entity_in.key}' in payload; skipped",
                    message_key="worldpack.import.warning.duplicate_entity_key",
                    message_params={"key": entity_in.key},
                    path=f"entities[{idx}].key",
                )
            )
            continue
        seen_entity_keys.add(entity_in.key)

        existing_entity = (
            db.query(WorldEntity)
            .filter(
                WorldEntity.novel_id == novel_id,
                WorldEntity.worldpack_pack_id == pack_id,
                WorldEntity.worldpack_key == entity_in.key,
            )
            .first()
        )
        linked_entity = None
        stripped_name = (entity_in.name or "").strip()
        if existing_entity is None and stripped_name:
            linked_entity = (
                db.query(WorldEntity)
                .filter(WorldEntity.novel_id == novel_id, WorldEntity.name == stripped_name)
                .first()
            )

        decision = plan_entity_import(
            existing_entity,
            linked_entity,
            entity_in,
            pack_id=pack_id,
            path=f"entities[{idx}].name",
        )
        for warning in decision.warnings:
            _append_warning(warnings, warning)
        if decision.track_desired_item:
            desired_entity_keys.add(entity_in.key)

        entity: WorldEntity | None = existing_entity
        skip_attribute_reconciliation = False
        if decision.action == "create":
            entity = WorldEntity(novel_id=novel_id, origin=WORLDPACK_ORIGIN, **decision.payload)
            db.add(entity)
            db.flush()
            counts.entities_created += 1
        elif decision.action == "link_existing":
            entity = linked_entity
            if entity is not None and decision.payload:
                for key, value in decision.payload.items():
                    setattr(entity, key, value)
                counts.entities_updated += 1
        elif decision.action == "update":
            if entity is not None and decision.payload:
                for key, value in decision.payload.items():
                    setattr(entity, key, value)
                counts.entities_updated += 1
        elif decision.action == "keep_existing":
            skip_attribute_reconciliation = True
        elif decision.action == "preserve" and decision.preserved_item is not None:
            preserved_entity_keys.add(decision.preserved_item)
        elif decision.action == "skip":
            entity = None

        if entity is None:
            continue

        entities_by_key[entity_in.key] = entity
        if skip_attribute_reconciliation:
            continue

        desired_attr_keys: set[str] = set()
        for attr_idx, attr_in in enumerate(entity_in.attributes):
            desired_attr_keys.add(attr_in.key)
            existing_attr = (
                db.query(WorldEntityAttribute)
                .filter(
                    WorldEntityAttribute.entity_id == entity.id,
                    WorldEntityAttribute.key == attr_in.key,
                )
                .first()
            )
            attr_decision = plan_attribute_import(
                existing_attr,
                attr_in,
                attribute_index=attr_idx,
                pack_id=pack_id,
            )
            if attr_decision.action == "create":
                attribute = WorldEntityAttribute(entity_id=entity.id, **attr_decision.payload)
                db.add(attribute)
                counts.attributes_created += 1
            elif attr_decision.action == "update":
                if existing_attr is not None and attr_decision.payload:
                    for key, value in attr_decision.payload.items():
                        setattr(existing_attr, key, value)
                    counts.attributes_updated += 1
            elif attr_decision.action == "preserve" and attr_decision.preserved_item is not None:
                preserved_attr_keys_by_entity.setdefault(entity_in.key, set()).add(attr_decision.preserved_item)

        existing_attrs = (
            db.query(WorldEntityAttribute)
            .filter(
                WorldEntityAttribute.entity_id == entity.id,
                WorldEntityAttribute.origin == WORLDPACK_ORIGIN,
                WorldEntityAttribute.worldpack_pack_id == pack_id,
            )
            .all()
        )
        for attr in existing_attrs:
            if attr.key not in desired_attr_keys:
                db.delete(attr)
                counts.attributes_deleted += 1

    return entities_by_key, desired_entity_keys, preserved_entity_keys, preserved_attr_keys_by_entity


def _sync_relationships(
    *,
    novel_id: int,
    relationships: list,
    entities_by_key: dict[str, WorldEntity],
    pack_id: str,
    db: Session,
    counts: WorldpackImportCountsResult,
    warnings: list[WorldpackImportWarningResult],
) -> tuple[set[tuple[int, int, str]], set[str]]:
    desired_relationship_sigs: set[tuple[int, int, str]] = set()
    preserved_relationship_sigs: set[str] = set()

    for idx, rel_in in enumerate(relationships):
        source = entities_by_key.get(rel_in.source_key)
        target = entities_by_key.get(rel_in.target_key)
        source_id = source.id if source is not None else None
        target_id = target.id if target is not None else None

        existing_rel = None
        label = (rel_in.label or "").strip()
        if source_id is not None and target_id is not None and label:
            signature = build_relationship_signature(source_id=source_id, target_id=target_id, label=label)
            existing_rel = (
                db.query(WorldRelationship)
                .filter(
                    WorldRelationship.novel_id == novel_id,
                    WorldRelationship.source_id == source_id,
                    WorldRelationship.target_id == target_id,
                    WorldRelationship.label_canonical == signature[2],
                )
                .first()
            )

        decision = plan_relationship_import(
            existing_rel,
            rel_in,
            pack_id=pack_id,
            source_id=source_id,
            target_id=target_id,
        )
        for warning in decision.warnings:
            fallback_path = f"relationships[{idx}]"
            if warning.code == "missing_relationship_label":
                fallback_path = f"relationships[{idx}].label"
            _append_warning(warnings, warning, fallback_path=fallback_path)

        signature = decision.payload.get("signature")
        if decision.track_desired_item and signature is not None:
            desired_relationship_sigs.add(signature)

        row_payload = {key: value for key, value in decision.payload.items() if key != "signature"}
        if decision.action == "create":
            relationship = WorldRelationship(novel_id=novel_id, **row_payload)
            db.add(relationship)
            counts.relationships_created += 1
        elif decision.action == "update":
            if existing_rel is not None and row_payload:
                for key, value in row_payload.items():
                    setattr(existing_rel, key, value)
                counts.relationships_updated += 1
        elif decision.action == "preserve" and decision.preserved_item is not None:
            preserved_relationship_sigs.add(decision.preserved_item)

    existing_rels = (
        db.query(WorldRelationship)
        .filter(
            WorldRelationship.novel_id == novel_id,
            WorldRelationship.origin == WORLDPACK_ORIGIN,
            WorldRelationship.worldpack_pack_id == pack_id,
        )
        .all()
    )
    for rel in existing_rels:
        if relationship_signature_from_row(rel) not in desired_relationship_sigs:
            db.delete(rel)
            counts.relationships_deleted += 1

    return desired_relationship_sigs, preserved_relationship_sigs


def _sync_systems(
    *,
    novel_id: int,
    systems: list,
    pack_id: str,
    db: Session,
    counts: WorldpackImportCountsResult,
    warnings: list[WorldpackImportWarningResult],
) -> tuple[set[str], set[str]]:
    desired_system_names: set[str] = set()
    preserved_system_names: set[str] = set()

    for idx, system_in in enumerate(systems):
        stripped_name = (system_in.name or "").strip()
        existing_system = None
        if stripped_name:
            existing_system = (
                db.query(WorldSystem)
                .filter(WorldSystem.novel_id == novel_id, WorldSystem.name == stripped_name)
                .first()
            )

        decision = plan_system_import(
            existing_system,
            system_in,
            pack_id=pack_id,
            path=f"systems[{idx}].name",
        )
        for warning in decision.warnings:
            _append_warning(warnings, warning)

        if decision.track_desired_item and stripped_name:
            desired_system_names.add(stripped_name)

        if decision.action == "create":
            system = WorldSystem(novel_id=novel_id, **decision.payload)
            db.add(system)
            counts.systems_created += 1
        elif decision.action == "update":
            if existing_system is not None and decision.payload:
                for key, value in decision.payload.items():
                    setattr(existing_system, key, value)
                counts.systems_updated += 1
        elif decision.action == "preserve" and decision.preserved_item is not None:
            preserved_system_names.add(decision.preserved_item)

    existing_systems = (
        db.query(WorldSystem)
        .filter(
            WorldSystem.novel_id == novel_id,
            WorldSystem.origin == WORLDPACK_ORIGIN,
            WorldSystem.worldpack_pack_id == pack_id,
        )
        .all()
    )
    for system in existing_systems:
        if system.name not in desired_system_names:
            db.delete(system)
            counts.systems_deleted += 1

    return desired_system_names, preserved_system_names


def _delete_removed_entities(
    *,
    novel_id: int,
    desired_entity_keys: set[str],
    pack_id: str,
    db: Session,
    counts: WorldpackImportCountsResult,
    warnings: list[WorldpackImportWarningResult],
) -> None:
    entity_query = db.query(WorldEntity).filter(
        WorldEntity.novel_id == novel_id,
        WorldEntity.origin == WORLDPACK_ORIGIN,
        WorldEntity.worldpack_pack_id == pack_id,
    )
    if desired_entity_keys:
        entity_query = entity_query.filter(~WorldEntity.worldpack_key.in_(sorted(desired_entity_keys)))
    entities_to_delete = entity_query.all()

    for entity in entities_to_delete:
        has_non_pack_attr = (
            db.query(WorldEntityAttribute.id)
            .filter(WorldEntityAttribute.entity_id == entity.id)
            .filter(
                ~and_(
                    WorldEntityAttribute.origin == WORLDPACK_ORIGIN,
                    WorldEntityAttribute.worldpack_pack_id == pack_id,
                )
            )
            .first()
            is not None
        )
        has_non_pack_rel = (
            db.query(WorldRelationship.id)
            .filter(WorldRelationship.novel_id == novel_id)
            .filter(or_(WorldRelationship.source_id == entity.id, WorldRelationship.target_id == entity.id))
            .filter(
                ~and_(
                    WorldRelationship.origin == WORLDPACK_ORIGIN,
                    WorldRelationship.worldpack_pack_id == pack_id,
                )
            )
            .first()
            is not None
        )
        decision = plan_entity_deletion(
            entity.worldpack_key,
            has_non_pack_attribute_dependency=has_non_pack_attr,
            has_non_pack_relationship_dependency=has_non_pack_rel,
        )
        for warning in decision.warnings:
            _append_warning(warnings, warning)
        if decision.action == "keep":
            continue

        attrs = (
            db.query(WorldEntityAttribute)
            .filter(
                WorldEntityAttribute.entity_id == entity.id,
                WorldEntityAttribute.origin == WORLDPACK_ORIGIN,
                WorldEntityAttribute.worldpack_pack_id == pack_id,
            )
            .all()
        )
        for attr in attrs:
            db.delete(attr)
            counts.attributes_deleted += 1

        db.delete(entity)
        counts.entities_deleted += 1


def import_worldpack_payload(
    novel_id: int,
    body: WorldpackV1Payload,
    db: Session,
) -> WorldpackImportResult:
    _ensure_novel_exists(novel_id, db)
    if body.schema_version != _WORLDPACK_SCHEMA_VERSION:
        raise UnsupportedWorldpackSchemaVersionError()

    pack_id = body.pack_id
    counts = WorldpackImportCountsResult()
    warnings: list[WorldpackImportWarningResult] = []

    try:
        for warning in collect_ambiguous_alias_warnings(body.entities):
            _append_warning(warnings, warning)

        entities_by_key, desired_entity_keys, preserved_entity_keys, preserved_attr_keys_by_entity = _sync_entities_and_attributes(
            novel_id=novel_id,
            body=body,
            pack_id=pack_id,
            db=db,
            counts=counts,
            warnings=warnings,
        )
        _, preserved_relationship_sigs = _sync_relationships(
            novel_id=novel_id,
            relationships=body.relationships,
            entities_by_key=entities_by_key,
            pack_id=pack_id,
            db=db,
            counts=counts,
            warnings=warnings,
        )
        _, preserved_system_names = _sync_systems(
            novel_id=novel_id,
            systems=body.systems,
            pack_id=pack_id,
            db=db,
            counts=counts,
            warnings=warnings,
        )
        _delete_removed_entities(
            novel_id=novel_id,
            desired_entity_keys=desired_entity_keys,
            pack_id=pack_id,
            db=db,
            counts=counts,
            warnings=warnings,
        )

        for optional_warning in (
            build_preserved_entity_warning(preserved_entity_keys),
            build_preserved_attribute_warning(preserved_attr_keys_by_entity),
            build_preserved_relationship_warning(preserved_relationship_sigs),
            build_preserved_system_warning(preserved_system_names),
        ):
            if optional_warning is not None:
                _append_warning(warnings, optional_warning)

        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise WorldpackImportConflictError() from exc

    return WorldpackImportResult(pack_id=pack_id, counts=counts, warnings=warnings)
