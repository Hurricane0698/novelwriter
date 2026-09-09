# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only


"""Atomic replacement of world-generation drafts; preserves other origins."""

from __future__ import annotations

import logging
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.world.write import build_relationship_signature
from app.models import WorldEntity, WorldRelationship, WorldSystem
from app.schemas import WorldGenerateResponse, WorldGenerateWarning
from .generation_schema import (
    WORLDGEN_ORIGIN,
    WorldGenLLMOutput,
    WorldGenSystem,
    _normalize_worldgen_system_display_type,
)
from .generation_normalization import (
    _norm,
    _norm_aliases,
    _worldgen_warning,
    _build_worldgen_system_data,
    _merge_worldgen_system_items,
)

logger = logging.getLogger(__name__)


def _delete_previous_worldgen_drafts(db: Session, novel_id: int) -> None:
    """Delete previous world generation draft rows without touching other draft sources.

    World generation owns only `origin=worldgen,status=draft` rows. This prevents the
    generator from deleting bootstrap drafts (e.g. chapter bootstrap extraction).
    """

    # Protect any entity referenced by a relationship we are NOT deleting.
    protected_entity_ids: set[int] = set()
    remaining_rels = (
        db.query(WorldRelationship.source_id, WorldRelationship.target_id)
        .filter(
            WorldRelationship.novel_id == novel_id,
            ~(
                (WorldRelationship.origin == WORLDGEN_ORIGIN)
                & (WorldRelationship.status == "draft")
            ),
        )
        .all()
    )
    for src_id, tgt_id in remaining_rels:
        if src_id is not None:
            protected_entity_ids.add(int(src_id))
        if tgt_id is not None:
            protected_entity_ids.add(int(tgt_id))

    # Relationships first (draft-only).
    db.query(WorldRelationship).filter(
        WorldRelationship.novel_id == novel_id,
        WorldRelationship.origin == WORLDGEN_ORIGIN,
        WorldRelationship.status == "draft",
    ).delete(synchronize_session=False)

    # Systems next (draft-only).
    db.query(WorldSystem).filter(
        WorldSystem.novel_id == novel_id,
        WorldSystem.origin == WORLDGEN_ORIGIN,
        WorldSystem.status == "draft",
    ).delete(synchronize_session=False)

    # Entities last (draft-only). Use ORM deletes for cascade behavior.
    entities = (
        db.query(WorldEntity)
        .filter(
            WorldEntity.novel_id == novel_id,
            WorldEntity.origin == WORLDGEN_ORIGIN,
            WorldEntity.status == "draft",
        )
        .all()
    )
    for e in entities:
        if int(e.id) in protected_entity_ids:
            continue
        db.delete(e)


def _stage_entities(
    *,
    db: Session,
    novel_id: int,
    extracted: WorldGenLLMOutput,
    warnings: list[WorldGenerateWarning],
    name_to_entity_id: dict[str, int],
) -> int:
    # Entities — stage all new rows, then one flush to assign ids for
    # relationship resolution.
    new_entities: list[WorldEntity] = []
    for idx, ent in enumerate(extracted.entities or []):
        name = _norm(ent.name)
        if not name:
            warnings.append(
                _worldgen_warning(
                    code="entity_skipped",
                    message_key="world.generate.warning.entity_missing_name",
                    message="Entity name is empty; skipped",
                    path=f"entities[{idx}].name",
                )
            )
            continue

        if name in name_to_entity_id:
            continue

        entity = WorldEntity(
            novel_id=novel_id,
            name=name,
            entity_type=_norm(ent.entity_type) or "Concept",
            description=_norm(ent.description),
            aliases=_norm_aliases(name=name, aliases=list(ent.aliases or [])),
            origin=WORLDGEN_ORIGIN,
            status="draft",
        )
        db.add(entity)
        new_entities.append(entity)
        name_to_entity_id[name] = 0  # reserved; real id assigned after flush

    if new_entities:
        db.flush()
        for entity in new_entities:
            name_to_entity_id[str(entity.name)] = int(entity.id)

    return len(new_entities)


def _stage_relationships(
    *,
    db: Session,
    novel_id: int,
    extracted: WorldGenLLMOutput,
    warnings: list[WorldGenerateWarning],
    name_to_entity_id: dict[str, int],
    relationship_keys_seen: set[tuple[int, int, str]],
) -> int:
    relationships_created = 0
    # Relationships
    for idx, rel in enumerate(extracted.relationships or []):
        src_name = _norm(rel.source)
        tgt_name = _norm(rel.target)
        label = _norm(rel.label)
        if not src_name or not tgt_name or not label:
            warnings.append(
                _worldgen_warning(
                    code="relationship_skipped",
                    message_key="world.generate.warning.relationship_missing_fields",
                    message="Relationship missing source/target/label; skipped",
                    path=f"relationships[{idx}]",
                )
            )
            continue

        src_id = name_to_entity_id.get(src_name)
        tgt_id = name_to_entity_id.get(tgt_name)
        if not src_id or not tgt_id:
            warnings.append(
                _worldgen_warning(
                    code="orphan_relationship_dropped",
                    message_key="world.generate.warning.relationship_unknown_entity",
                    message="Relationship references unknown entity; dropped",
                    message_params={"source": src_name, "target": tgt_name},
                    path=f"relationships[{idx}]",
                )
            )
            continue

        if int(src_id) == int(tgt_id):
            warnings.append(
                _worldgen_warning(
                    code="relationship_skipped",
                    message_key="world.generate.warning.relationship_self_reference",
                    message="Relationship source and target are identical; skipped",
                    message_params={"entity": src_name},
                    path=f"relationships[{idx}]",
                )
            )
            continue

        rel_key = build_relationship_signature(
            source_id=int(src_id),
            target_id=int(tgt_id),
            label=label,
        )
        if rel_key in relationship_keys_seen:
            warnings.append(
                _worldgen_warning(
                    code="relationship_duplicate_dropped",
                    message_key="world.generate.warning.relationship_duplicate",
                    message="Duplicate relationship; dropped",
                    message_params={"label": label},
                    path=f"relationships[{idx}]",
                )
            )
            continue
        relationship_keys_seen.add(rel_key)

        relationship = WorldRelationship(
            novel_id=novel_id,
            source_id=int(src_id),
            target_id=int(tgt_id),
            label=label,
            description=_norm(rel.description),
            visibility="reference",
            origin=WORLDGEN_ORIGIN,
            status="draft",
        )
        db.add(relationship)
        relationships_created += 1

    return relationships_created


def _stage_systems(
    *,
    db: Session,
    novel_id: int,
    extracted: WorldGenLLMOutput,
    warnings: list[WorldGenerateWarning],
    existing_system_names: set[str],
) -> int:
    systems_created = 0
    # Systems (visibility=reference; display_type chosen by LLM draft)
    seen_system_names: set[str] = set()
    for idx, sys in enumerate(extracted.systems or []):
        name = _norm(sys.name)
        if not name:
            warnings.append(
                _worldgen_warning(
                    code="system_skipped",
                    message_key="world.generate.warning.system_missing_name",
                    message="System name is empty; skipped",
                    path=f"systems[{idx}].name",
                )
            )
            continue
        if name in seen_system_names:
            warnings.append(
                _worldgen_warning(
                    code="system_duplicate_dropped",
                    message_key="world.generate.warning.system_duplicate",
                    message="Duplicate system name; dropped",
                    message_params={"name": name},
                    path=f"systems[{idx}].name",
                )
            )
            continue
        seen_system_names.add(name)

        if name in existing_system_names:
            warnings.append(
                _worldgen_warning(
                    code="system_conflict_skipped",
                    message_key="world.generate.warning.system_name_conflict",
                    message="System name already exists; skipped",
                    message_params={"name": name},
                    path=f"systems[{idx}].name",
                )
            )
            continue

        display_type, data = _build_worldgen_system_data(
            system=WorldGenSystem(
                name=name,
                description=_norm(sys.description),
                display_type=_normalize_worldgen_system_display_type(sys.display_type),
                items=_merge_worldgen_system_items(
                    list(sys.items or []),
                    display_type=_normalize_worldgen_system_display_type(
                        sys.display_type
                    ),
                ),
                constraints=list(sys.constraints or []),
            ),
            system_index=idx,
            warnings=warnings,
        )

        constraints = []
        seen_constraints: set[str] = set()
        for c in sys.constraints or []:
            c = _norm(c)
            if c:
                if c in seen_constraints:
                    continue
                seen_constraints.add(c)
                constraints.append(c)

        system = WorldSystem(
            novel_id=novel_id,
            name=name,
            display_type=display_type,
            description=_norm(sys.description),
            data=data,
            constraints=constraints,
            visibility="reference",
            origin=WORLDGEN_ORIGIN,
            status="draft",
        )
        db.add(system)
        systems_created += 1

    return systems_created


def persist_world_drafts(
    *,
    db: Session,
    novel_id: int,
    extracted: WorldGenLLMOutput,
    warnings: list[WorldGenerateWarning],
) -> WorldGenerateResponse:
    try:
        _delete_previous_worldgen_drafts(db, novel_id)

        # Preload current entities/systems for conflict-free inserts.
        name_to_entity_id: dict[str, int] = {}
        for entity_id, name in (
            db.query(WorldEntity.id, WorldEntity.name)
            .filter(WorldEntity.novel_id == novel_id)
            .all()
        ):
            if name:
                name_to_entity_id[str(name)] = int(entity_id)

        existing_system_names = {
            str(name)
            for (name,) in db.query(WorldSystem.name)
            .filter(WorldSystem.novel_id == novel_id)
            .all()
            if name
        }

        relationship_keys_seen: set[tuple[int, int, str]] = set()
        for src_id, tgt_id, label_canonical in (
            db.query(
                WorldRelationship.source_id,
                WorldRelationship.target_id,
                WorldRelationship.label_canonical,
            )
            .filter(WorldRelationship.novel_id == novel_id)
            .all()
        ):
            if src_id is None or tgt_id is None:
                continue
            signature = build_relationship_signature(
                source_id=int(src_id),
                target_id=int(tgt_id),
                label_canonical=str(label_canonical or ""),
            )
            if not signature[2]:
                continue
            relationship_keys_seen.add(signature)

        entities_created = _stage_entities(
            db=db,
            novel_id=novel_id,
            extracted=extracted,
            warnings=warnings,
            name_to_entity_id=name_to_entity_id,
        )
        relationships_created = _stage_relationships(
            db=db,
            novel_id=novel_id,
            extracted=extracted,
            warnings=warnings,
            name_to_entity_id=name_to_entity_id,
            relationship_keys_seen=relationship_keys_seen,
        )
        systems_created = _stage_systems(
            db=db,
            novel_id=novel_id,
            extracted=extracted,
            warnings=warnings,
            existing_system_names=existing_system_names,
        )

        db.commit()
        return WorldGenerateResponse(
            entities_created=entities_created,
            relationships_created=relationships_created,
            systems_created=systems_created,
            warnings=warnings,
        )
    except IntegrityError:
        db.rollback()
        # Expected occasionally under concurrent writes (e.g. parallel generates).
        logger.warning(
            "world_gen: persist conflict for novel %s", novel_id, exc_info=True
        )
        raise
    except Exception:
        db.rollback()
        logger.exception("world_gen: persist failed for novel %s", novel_id)
        raise
