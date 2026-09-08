# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""DB-backed scope snapshot loading for copilot."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.indexing import (
    WINDOW_INDEX_STATUS_FRESH,
    WindowIndexLifecycleSnapshot,
    inspect_window_index_lifecycle,
)
from app.models import (
    Novel,
    WorldEntity,
    WorldEntityAttribute,
    WorldRelationship,
    WorldSystem,
)

from .scope_shared import (
    CopilotFocusVariant,
    CopilotRuntimeProfile,
    EntityLookupRef,
    MAX_SCOPE_ENTITIES,
    MAX_SCOPE_RELATIONSHIPS,
    MAX_SCOPE_SYSTEMS,
    NovelScopeValue,
    ScopeSnapshot,
    SystemLookupRef,
    normalize_lookup_key,
)


def derive_runtime_profile(
    mode: str, scope: str, context: dict | None
) -> CopilotRuntimeProfile:
    """Derive the bounded runtime profile used for isolation and preload policy."""
    if mode == "draft_cleanup":
        return "draft_governance"
    if scope == "whole_book":
        return "broad_exploration"
    return "focused_research"


def derive_focus_variant(
    mode: str, scope: str, context: dict | None
) -> CopilotFocusVariant:
    """Derive the detailed workbench focus within the runtime profile."""
    if mode == "draft_cleanup":
        return "draft"
    if scope == "whole_book":
        return "whole_book"
    if context and context.get("tab") == "relationships":
        return "relationship"
    return "entity"


def _load_attributes_for_entities(
    db: Session,
    entity_ids: list[int],
) -> dict[int, list[WorldEntityAttribute]]:
    if not entity_ids:
        return {}

    attrs = (
        db.query(WorldEntityAttribute)
        .filter(WorldEntityAttribute.entity_id.in_(entity_ids))
        .order_by(WorldEntityAttribute.sort_order)
        .all()
    )
    attrs_by_entity: dict[int, list[WorldEntityAttribute]] = {}
    for attr in attrs:
        attrs_by_entity.setdefault(attr.entity_id, []).append(attr)
    return attrs_by_entity


def _build_scope_snapshot(
    *,
    novel: Novel,
    profile: CopilotRuntimeProfile,
    focus_variant: CopilotFocusVariant,
    focus_entity_id: int | None,
    entities: list[WorldEntity],
    relationships: list[WorldRelationship],
    systems: list[WorldSystem],
    attributes_by_entity: dict[int, list[WorldEntityAttribute]],
    window_index_state: WindowIndexLifecycleSnapshot,
    novel_entity_refs_by_name_key: dict[str, tuple[EntityLookupRef, ...]],
    novel_system_refs_by_name_key: dict[str, tuple[SystemLookupRef, ...]],
) -> ScopeSnapshot:
    entities_by_id = {entity.id: entity for entity in entities}
    return ScopeSnapshot(
        novel=NovelScopeValue(
            id=novel.id,
            title=novel.title,
            author=novel.author,
            language=novel.language,
            window_index=(
                novel.window_index
                if window_index_state.status == WINDOW_INDEX_STATUS_FRESH
                and window_index_state.has_payload
                else None
            ),
        ),
        novel_language=novel.language or "zh",
        entities=entities,
        entities_by_id=entities_by_id,
        relationships=relationships,
        systems=systems,
        attributes_by_entity=attributes_by_entity,
        draft_entities=[entity for entity in entities if entity.status == "draft"],
        draft_relationships=[
            relationship
            for relationship in relationships
            if relationship.status == "draft"
        ],
        draft_systems=[system for system in systems if system.status == "draft"],
        profile=profile,
        focus_variant=focus_variant,
        focus_entity_id=focus_entity_id,
        window_index_state=window_index_state,
        novel_entity_refs_by_name_key=novel_entity_refs_by_name_key,
        novel_system_refs_by_name_key=novel_system_refs_by_name_key,
    )


def _load_novel_entity_lookup(
    db: Session,
    novel: Novel,
) -> dict[str, tuple[EntityLookupRef, ...]]:
    refs_by_key: dict[str, list[EntityLookupRef]] = {}
    seen: set[tuple[str, int]] = set()
    rows = db.query(
        WorldEntity.id, WorldEntity.name, WorldEntity.status, WorldEntity.aliases
    ).filter(WorldEntity.novel_id == novel.id)
    for entity in rows:
        ref = EntityLookupRef(
            entity_id=int(entity.id),
            name=str(entity.name or "").strip(),
            status=str(entity.status or ""),
        )
        for raw_value in (entity.name, *(entity.aliases or [])):
            key = normalize_lookup_key(raw_value, language=novel.language)
            if not key:
                continue
            dedupe_key = (key, ref.entity_id)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            refs_by_key.setdefault(key, []).append(ref)
    return {key: tuple(values) for key, values in refs_by_key.items()}


def _load_novel_system_lookup(
    db: Session,
    novel: Novel,
) -> dict[str, tuple[SystemLookupRef, ...]]:
    refs_by_key: dict[str, list[SystemLookupRef]] = {}
    seen: set[tuple[str, int]] = set()
    rows = db.query(WorldSystem.id, WorldSystem.name, WorldSystem.status).filter(
        WorldSystem.novel_id == novel.id
    )
    for system in rows:
        key = normalize_lookup_key(system.name, language=novel.language)
        if not key:
            continue
        ref = SystemLookupRef(
            system_id=int(system.id),
            name=str(system.name or "").strip(),
            status=str(system.status or ""),
        )
        dedupe_key = (key, ref.system_id)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        refs_by_key.setdefault(key, []).append(ref)
    return {key: tuple(values) for key, values in refs_by_key.items()}


def _load_broad_exploration_snapshot(
    db: Session,
    novel: Novel,
    *,
    focus_variant: CopilotFocusVariant,
    window_index_state: WindowIndexLifecycleSnapshot,
) -> ScopeSnapshot:
    novel_id = novel.id
    novel_entity_refs_by_name_key = _load_novel_entity_lookup(db, novel)
    novel_system_refs_by_name_key = _load_novel_system_lookup(db, novel)
    entities = (
        db.query(WorldEntity)
        .filter(WorldEntity.novel_id == novel_id)
        .limit(MAX_SCOPE_ENTITIES)
        .all()
    )
    relationships = (
        db.query(WorldRelationship)
        .filter(WorldRelationship.novel_id == novel_id)
        .limit(MAX_SCOPE_RELATIONSHIPS)
        .all()
    )
    systems = (
        db.query(WorldSystem)
        .filter(WorldSystem.novel_id == novel_id)
        .limit(MAX_SCOPE_SYSTEMS)
        .all()
    )
    attributes_by_entity = _load_attributes_for_entities(
        db, [entity.id for entity in entities]
    )
    return _build_scope_snapshot(
        novel=novel,
        profile="broad_exploration",
        focus_variant=focus_variant,
        focus_entity_id=None,
        entities=entities,
        relationships=relationships,
        systems=systems,
        attributes_by_entity=attributes_by_entity,
        window_index_state=window_index_state,
        novel_entity_refs_by_name_key=novel_entity_refs_by_name_key,
        novel_system_refs_by_name_key=novel_system_refs_by_name_key,
    )


def _load_focused_research_snapshot(
    db: Session,
    novel: Novel,
    *,
    focus_variant: CopilotFocusVariant,
    focus_entity_id: int | None,
    window_index_state: WindowIndexLifecycleSnapshot,
) -> ScopeSnapshot:
    novel_id = novel.id
    novel_entity_refs_by_name_key = _load_novel_entity_lookup(db, novel)
    novel_system_refs_by_name_key = _load_novel_system_lookup(db, novel)
    entity_query = db.query(WorldEntity).filter(WorldEntity.novel_id == novel_id)
    relationship_query = db.query(WorldRelationship).filter(
        WorldRelationship.novel_id == novel_id
    )

    if focus_entity_id is not None:
        relationships = (
            relationship_query.filter(
                (WorldRelationship.source_id == focus_entity_id)
                | (WorldRelationship.target_id == focus_entity_id),
            )
            .limit(MAX_SCOPE_RELATIONSHIPS)
            .all()
        )

        entity_ids = {focus_entity_id}
        for relationship in relationships:
            entity_ids.add(relationship.source_id)
            entity_ids.add(relationship.target_id)

        entities = (
            entity_query.filter(WorldEntity.id.in_(entity_ids))
            .limit(MAX_SCOPE_ENTITIES)
            .all()
        )
    else:
        entities = entity_query.limit(min(MAX_SCOPE_ENTITIES, 16)).all()
        entity_ids = {entity.id for entity in entities}
        if entity_ids:
            relationships = (
                relationship_query.filter(
                    (WorldRelationship.source_id.in_(entity_ids))
                    | (WorldRelationship.target_id.in_(entity_ids)),
                )
                .limit(min(MAX_SCOPE_RELATIONSHIPS, 20))
                .all()
            )
        else:
            relationships = []

    attributes_by_entity = _load_attributes_for_entities(
        db, [entity.id for entity in entities]
    )
    return _build_scope_snapshot(
        novel=novel,
        profile="focused_research",
        focus_variant=focus_variant,
        focus_entity_id=focus_entity_id,
        entities=entities,
        relationships=relationships,
        systems=[],
        attributes_by_entity=attributes_by_entity,
        window_index_state=window_index_state,
        novel_entity_refs_by_name_key=novel_entity_refs_by_name_key,
        novel_system_refs_by_name_key=novel_system_refs_by_name_key,
    )


def _load_draft_governance_snapshot(
    db: Session,
    novel: Novel,
    *,
    window_index_state: WindowIndexLifecycleSnapshot,
) -> ScopeSnapshot:
    novel_id = novel.id
    novel_entity_refs_by_name_key = _load_novel_entity_lookup(db, novel)
    novel_system_refs_by_name_key = _load_novel_system_lookup(db, novel)
    draft_entities = (
        db.query(WorldEntity)
        .filter(WorldEntity.novel_id == novel_id, WorldEntity.status == "draft")
        .limit(MAX_SCOPE_ENTITIES)
        .all()
    )
    draft_relationships = (
        db.query(WorldRelationship)
        .filter(
            WorldRelationship.novel_id == novel_id, WorldRelationship.status == "draft"
        )
        .limit(MAX_SCOPE_RELATIONSHIPS)
        .all()
    )
    draft_systems = (
        db.query(WorldSystem)
        .filter(WorldSystem.novel_id == novel_id, WorldSystem.status == "draft")
        .limit(MAX_SCOPE_SYSTEMS)
        .all()
    )

    entity_ids = {entity.id for entity in draft_entities}
    for relationship in draft_relationships:
        entity_ids.add(relationship.source_id)
        entity_ids.add(relationship.target_id)

    entities = (
        db.query(WorldEntity)
        .filter(WorldEntity.novel_id == novel_id, WorldEntity.id.in_(entity_ids))
        .all()
        if entity_ids
        else []
    )
    attributes_by_entity = _load_attributes_for_entities(
        db, [entity.id for entity in entities]
    )
    return _build_scope_snapshot(
        novel=novel,
        profile="draft_governance",
        focus_variant="draft",
        focus_entity_id=None,
        entities=entities,
        relationships=draft_relationships,
        systems=draft_systems,
        attributes_by_entity=attributes_by_entity,
        window_index_state=window_index_state,
        novel_entity_refs_by_name_key=novel_entity_refs_by_name_key,
        novel_system_refs_by_name_key=novel_system_refs_by_name_key,
    )


def load_scope_snapshot(
    db: Session, novel: Novel, mode: str, scope: str, context: dict | None
) -> ScopeSnapshot:
    """Load world-model state relevant to the current copilot scope."""
    profile = derive_runtime_profile(mode, scope, context)
    focus_variant = derive_focus_variant(mode, scope, context)
    window_index_state = inspect_window_index_lifecycle(novel, db=db)
    focus_entity_id = (context or {}).get("entity_id")
    if not isinstance(focus_entity_id, int):
        focus_entity_id = None

    if profile == "draft_governance":
        return _load_draft_governance_snapshot(
            db, novel, window_index_state=window_index_state
        )
    if profile == "focused_research":
        return _load_focused_research_snapshot(
            db,
            novel,
            focus_variant=focus_variant,
            focus_entity_id=focus_entity_id,
            window_index_state=window_index_state,
        )
    return _load_broad_exploration_snapshot(
        db,
        novel,
        focus_variant=focus_variant,
        window_index_state=window_index_state,
    )
