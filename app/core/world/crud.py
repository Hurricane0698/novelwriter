# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Shared application helpers for novel-scoped world-model CRUD flows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence, TypeVar

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.world.write import (
    InvalidSystemDisplayTypeError,
    RelationshipConflictError,
    ensure_relationship_is_unique,
    normalize_system_data_for_write,
    promote_ai_draft_origin_to_manual,
    promote_worldpack_origin_to_manual,
)
from app.models import Novel, WorldEntity, WorldEntityAttribute, WorldRelationship, WorldSystem

_RowT = TypeVar("_RowT", WorldEntity, WorldEntityAttribute, WorldRelationship, WorldSystem)


@dataclass(slots=True)
class WorldCrudError(RuntimeError):
    code: str
    message: str
    status_code: int

    def __str__(self) -> str:
        return self.message


@dataclass(slots=True)
class WorldCrudDetailError(RuntimeError):
    detail: object
    status_code: int


def load_novel(novel_id: int, db: Session) -> Novel:
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if novel is None:
        raise WorldCrudError(code="novel_not_found", message="Novel not found", status_code=404)
    return novel


def load_entity(novel_id: int, entity_id: int, db: Session) -> WorldEntity:
    entity = db.query(WorldEntity).filter(WorldEntity.id == entity_id, WorldEntity.novel_id == novel_id).first()
    if entity is None:
        raise WorldCrudError(code="entity_not_found", message="Entity not found", status_code=404)
    return entity


def load_attribute(entity_id: int, attribute_id: int, db: Session) -> WorldEntityAttribute:
    attribute = db.query(WorldEntityAttribute).filter(
        WorldEntityAttribute.id == attribute_id,
        WorldEntityAttribute.entity_id == entity_id,
    ).first()
    if attribute is None:
        raise WorldCrudError(code="attribute_not_found", message="Attribute not found", status_code=404)
    return attribute


def load_relationship(novel_id: int, relationship_id: int, db: Session) -> WorldRelationship:
    relationship = db.query(WorldRelationship).filter(
        WorldRelationship.id == relationship_id,
        WorldRelationship.novel_id == novel_id,
    ).first()
    if relationship is None:
        raise WorldCrudError(code="relationship_not_found", message="Relationship not found", status_code=404)
    return relationship


def load_system(novel_id: int, system_id: int, db: Session) -> WorldSystem:
    system = db.query(WorldSystem).filter(WorldSystem.id == system_id, WorldSystem.novel_id == novel_id).first()
    if system is None:
        raise WorldCrudError(code="system_not_found", message="System not found", status_code=404)
    return system


def ensure_unique_relationship_write(
    db: Session,
    *,
    novel_id: int,
    source_id: int,
    target_id: int,
    label: str,
    exclude_relationship_id: int | None = None,
) -> None:
    try:
        ensure_relationship_is_unique(
            db,
            novel_id=novel_id,
            source_id=source_id,
            target_id=target_id,
            label=label,
            exclude_relationship_id=exclude_relationship_id,
        )
    except RelationshipConflictError as exc:
        raise WorldCrudError(code="relationship_conflict", message="Relationship conflict", status_code=409) from exc


def commit_world_change(
    db: Session,
    *,
    conflict_code: str,
    conflict_message: str,
) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise WorldCrudError(code=conflict_code, message=conflict_message, status_code=409) from exc


def flush_world_change(
    db: Session,
    *,
    conflict_code: str,
    conflict_message: str,
) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        nested = db.get_nested_transaction()
        if nested is not None:
            nested.rollback()
        else:
            db.rollback()
        raise WorldCrudError(code=conflict_code, message=conflict_message, status_code=409) from exc


def stage_create_entity(novel_id: int, data: Mapping[str, Any], db: Session) -> WorldEntity:
    load_novel(novel_id, db)
    entity = WorldEntity(novel_id=novel_id, **dict(data))
    db.add(entity)
    flush_world_change(
        db,
        conflict_code="entity_name_conflict",
        conflict_message="Entity with this name already exists in this novel",
    )
    return entity


def create_entity(novel_id: int, data: Mapping[str, Any], db: Session) -> WorldEntity:
    entity = stage_create_entity(novel_id, data, db)
    return _commit_and_refresh(
        db,
        row=entity,
        conflict_code="entity_name_conflict",
        conflict_message="Entity with this name already exists in this novel",
    )


def stage_update_entity(novel_id: int, entity_id: int, data: Mapping[str, Any], db: Session) -> WorldEntity:
    entity = load_entity(novel_id, entity_id, db)
    update_data = dict(data)
    _apply_updates(entity, update_data)
    if update_data:
        promote_worldpack_origin_to_manual(entity)
        promote_ai_draft_origin_to_manual(entity)
        flush_world_change(
            db,
            conflict_code="entity_name_conflict",
            conflict_message="Entity name conflict",
        )
    return entity


def update_entity(novel_id: int, entity_id: int, data: Mapping[str, Any], db: Session) -> WorldEntity:
    entity = stage_update_entity(novel_id, entity_id, data, db)
    return _commit_and_refresh(
        db,
        row=entity,
        conflict_code="entity_name_conflict",
        conflict_message="Entity name conflict",
    )


def stage_create_attribute(
    novel_id: int,
    entity_id: int,
    data: Mapping[str, Any],
    db: Session,
) -> WorldEntityAttribute:
    entity = load_entity(novel_id, entity_id, db)
    promote_ai_draft_origin_to_manual(entity)
    attribute = WorldEntityAttribute(entity_id=entity_id, **dict(data))
    db.add(attribute)
    flush_world_change(
        db,
        conflict_code="attribute_key_conflict",
        conflict_message="Attribute with this key already exists for this entity",
    )
    return attribute


def create_attribute(novel_id: int, entity_id: int, data: Mapping[str, Any], db: Session) -> WorldEntityAttribute:
    attribute = stage_create_attribute(novel_id, entity_id, data, db)
    return _commit_and_refresh(
        db,
        row=attribute,
        conflict_code="attribute_key_conflict",
        conflict_message="Attribute with this key already exists for this entity",
    )


def stage_update_attribute(
    novel_id: int,
    entity_id: int,
    attribute_id: int,
    data: Mapping[str, Any],
    db: Session,
) -> WorldEntityAttribute:
    entity = load_entity(novel_id, entity_id, db)
    attribute = load_attribute(entity_id, attribute_id, db)
    update_data = dict(data)
    _apply_updates(attribute, update_data)
    if update_data:
        promote_worldpack_origin_to_manual(attribute)
        promote_ai_draft_origin_to_manual(entity)
        flush_world_change(
            db,
            conflict_code="attribute_key_conflict",
            conflict_message="Attribute key conflict",
        )
    return attribute


def update_attribute(
    novel_id: int,
    entity_id: int,
    attribute_id: int,
    data: Mapping[str, Any],
    db: Session,
) -> WorldEntityAttribute:
    attribute = stage_update_attribute(novel_id, entity_id, attribute_id, data, db)
    return _commit_and_refresh(
        db,
        row=attribute,
        conflict_code="attribute_key_conflict",
        conflict_message="Attribute key conflict",
    )


def delete_entity(novel_id: int, entity_id: int, db: Session) -> None:
    entity = load_entity(novel_id, entity_id, db)
    _delete_row(
        db,
        row=entity,
        conflict_code="entity_delete_conflict",
        conflict_message="Entity delete conflict",
    )


def delete_attribute(novel_id: int, entity_id: int, attribute_id: int, db: Session) -> None:
    entity = load_entity(novel_id, entity_id, db)
    attribute = load_attribute(entity_id, attribute_id, db)
    promote_ai_draft_origin_to_manual(entity)
    _delete_row(
        db,
        row=attribute,
        conflict_code="attribute_delete_conflict",
        conflict_message="Attribute delete conflict",
    )


def reorder_attributes(novel_id: int, entity_id: int, order: Sequence[int], db: Session) -> None:
    entity = load_entity(novel_id, entity_id, db)
    promote_ai_draft_origin_to_manual(entity)
    for index, attribute_id in enumerate(order):
        db.query(WorldEntityAttribute).filter(
            WorldEntityAttribute.id == attribute_id,
            WorldEntityAttribute.entity_id == entity_id,
        ).update({"sort_order": index})
    commit_world_change(
        db,
        conflict_code="attribute_reorder_conflict",
        conflict_message="Attribute reorder conflict",
    )


def stage_create_relationship(novel_id: int, data: Mapping[str, Any], db: Session) -> WorldRelationship:
    payload = dict(data)
    load_novel(novel_id, db)
    source_id = int(payload["source_id"])
    target_id = int(payload["target_id"])
    label = str(payload["label"])
    load_entity(novel_id, source_id, db)
    load_entity(novel_id, target_id, db)
    ensure_unique_relationship_write(
        db,
        novel_id=novel_id,
        source_id=source_id,
        target_id=target_id,
        label=label,
    )
    relationship = WorldRelationship(novel_id=novel_id, **payload)
    db.add(relationship)
    flush_world_change(
        db,
        conflict_code="relationship_conflict",
        conflict_message="Relationship conflict",
    )
    return relationship


def create_relationship(novel_id: int, data: Mapping[str, Any], db: Session) -> WorldRelationship:
    relationship = stage_create_relationship(novel_id, data, db)
    return _commit_and_refresh(
        db,
        row=relationship,
        conflict_code="relationship_conflict",
        conflict_message="Relationship conflict",
    )


def stage_update_relationship(
    novel_id: int,
    relationship_id: int,
    data: Mapping[str, Any],
    db: Session,
) -> WorldRelationship:
    relationship = load_relationship(novel_id, relationship_id, db)
    update_data = dict(data)
    if "label" in update_data:
        ensure_unique_relationship_write(
            db,
            novel_id=novel_id,
            source_id=relationship.source_id,
            target_id=relationship.target_id,
            label=str(update_data["label"]),
            exclude_relationship_id=relationship.id,
        )
    _apply_updates(relationship, update_data)
    if update_data:
        promote_worldpack_origin_to_manual(relationship)
        promote_ai_draft_origin_to_manual(relationship)
        flush_world_change(
            db,
            conflict_code="relationship_conflict",
            conflict_message="Relationship conflict",
        )
    return relationship


def update_relationship(
    novel_id: int,
    relationship_id: int,
    data: Mapping[str, Any],
    db: Session,
) -> WorldRelationship:
    relationship = stage_update_relationship(novel_id, relationship_id, data, db)
    return _commit_and_refresh(
        db,
        row=relationship,
        conflict_code="relationship_conflict",
        conflict_message="Relationship conflict",
    )


def delete_relationship(novel_id: int, relationship_id: int, db: Session) -> None:
    relationship = load_relationship(novel_id, relationship_id, db)
    _delete_row(
        db,
        row=relationship,
        conflict_code="relationship_delete_conflict",
        conflict_message="Relationship delete conflict",
    )


def delete_system(novel_id: int, system_id: int, db: Session) -> None:
    system = load_system(novel_id, system_id, db)
    _delete_row(
        db,
        row=system,
        conflict_code="system_delete_conflict",
        conflict_message="System delete conflict",
    )


def batch_confirm_entities(novel_id: int, ids: Sequence[int], db: Session) -> int:
    return _batch_confirm_rows(
        db,
        model=WorldEntity,
        novel_id=novel_id,
        ids=ids,
        conflict_code="entity_confirm_conflict",
        conflict_message="Entity confirm conflict",
    )


def batch_reject_entities(novel_id: int, ids: Sequence[int], db: Session) -> int:
    return _batch_reject_rows(
        db,
        model=WorldEntity,
        novel_id=novel_id,
        ids=ids,
        conflict_code="entity_reject_conflict",
        conflict_message="Entity reject conflict",
    )


def batch_confirm_relationships(novel_id: int, ids: Sequence[int], db: Session) -> int:
    return _batch_confirm_rows(
        db,
        model=WorldRelationship,
        novel_id=novel_id,
        ids=ids,
        conflict_code="relationship_confirm_conflict",
        conflict_message="Relationship confirm conflict",
    )


def batch_reject_relationships(novel_id: int, ids: Sequence[int], db: Session) -> int:
    return _batch_reject_rows(
        db,
        model=WorldRelationship,
        novel_id=novel_id,
        ids=ids,
        conflict_code="relationship_reject_conflict",
        conflict_message="Relationship reject conflict",
    )


def stage_create_system(novel_id: int, data: Mapping[str, Any], db: Session) -> WorldSystem:
    payload = dict(data)
    load_novel(novel_id, db)
    payload["data"] = _normalize_system_payload(payload["display_type"], payload.get("data"))
    system = WorldSystem(novel_id=novel_id, **payload)
    db.add(system)
    flush_world_change(
        db,
        conflict_code="system_name_conflict",
        conflict_message="System with this name already exists in this novel",
    )
    return system


def create_system(novel_id: int, data: Mapping[str, Any], db: Session) -> WorldSystem:
    system = stage_create_system(novel_id, data, db)
    return _commit_and_refresh(
        db,
        row=system,
        conflict_code="system_name_conflict",
        conflict_message="System with this name already exists in this novel",
    )


def stage_update_system(novel_id: int, system_id: int, data: Mapping[str, Any], db: Session) -> WorldSystem:
    system = load_system(novel_id, system_id, db)
    update_data = dict(data)
    _apply_updates(system, update_data)
    if "data" in update_data or "display_type" in update_data:
        system.data = _normalize_system_payload(system.display_type, system.data)
    if update_data:
        promote_worldpack_origin_to_manual(system)
        promote_ai_draft_origin_to_manual(system)
        flush_world_change(
            db,
            conflict_code="system_name_conflict",
            conflict_message="System name conflict",
        )
    return system


def update_system(novel_id: int, system_id: int, data: Mapping[str, Any], db: Session) -> WorldSystem:
    system = stage_update_system(novel_id, system_id, data, db)
    return _commit_and_refresh(
        db,
        row=system,
        conflict_code="system_name_conflict",
        conflict_message="System name conflict",
    )


def batch_confirm_systems(novel_id: int, ids: Sequence[int], db: Session) -> int:
    return _batch_confirm_rows(
        db,
        model=WorldSystem,
        novel_id=novel_id,
        ids=ids,
        conflict_code="system_confirm_conflict",
        conflict_message="System confirm conflict",
    )


def batch_reject_systems(novel_id: int, ids: Sequence[int], db: Session) -> int:
    return _batch_reject_rows(
        db,
        model=WorldSystem,
        novel_id=novel_id,
        ids=ids,
        conflict_code="system_reject_conflict",
        conflict_message="System reject conflict",
    )


def _delete_row(
    db: Session,
    *,
    row: WorldEntity | WorldEntityAttribute | WorldRelationship | WorldSystem,
    conflict_code: str,
    conflict_message: str,
) -> None:
    db.delete(row)
    commit_world_change(db, conflict_code=conflict_code, conflict_message=conflict_message)


def _batch_confirm_rows(
    db: Session,
    *,
    model: type[WorldEntity] | type[WorldRelationship] | type[WorldSystem],
    novel_id: int,
    ids: Sequence[int],
    conflict_code: str,
    conflict_message: str,
) -> int:
    load_novel(novel_id, db)
    count = (
        db.query(model)
        .filter(
            model.novel_id == novel_id,
            model.id.in_(ids),
            model.status == "draft",
        )
        .update({"status": "confirmed"}, synchronize_session="fetch")
    )
    commit_world_change(db, conflict_code=conflict_code, conflict_message=conflict_message)
    return count


def _batch_reject_rows(
    db: Session,
    *,
    model: type[WorldEntity] | type[WorldRelationship] | type[WorldSystem],
    novel_id: int,
    ids: Sequence[int],
    conflict_code: str,
    conflict_message: str,
) -> int:
    load_novel(novel_id, db)
    rows = (
        db.query(model)
        .filter(
            model.novel_id == novel_id,
            model.id.in_(ids),
            model.status == "draft",
        )
        .all()
    )
    for row in rows:
        db.delete(row)
    commit_world_change(db, conflict_code=conflict_code, conflict_message=conflict_message)
    return len(rows)


def _apply_updates(
    row: WorldEntity | WorldEntityAttribute | WorldRelationship | WorldSystem,
    data: Mapping[str, Any],
) -> None:
    for key, value in data.items():
        setattr(row, key, value)


def _commit_and_refresh(
    db: Session,
    *,
    row: _RowT,
    conflict_code: str,
    conflict_message: str,
) -> _RowT:
    commit_world_change(db, conflict_code=conflict_code, conflict_message=conflict_message)
    db.refresh(row)
    return row


def _normalize_system_payload(display_type: str, data: Any) -> dict:
    try:
        return normalize_system_data_for_write(display_type, data)
    except ValidationError as exc:
        raise WorldCrudDetailError(detail=exc.errors(), status_code=422) from exc
    except InvalidSystemDisplayTypeError as exc:
        raise WorldCrudError(code="invalid_system_display_type", message=str(exc), status_code=422) from exc
