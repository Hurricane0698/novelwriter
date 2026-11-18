# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Shared support for copilot suggestion/apply tests."""

from app.models import Novel, WorldEntityAttribute


def make_scope_snapshot(db, entities, relationships, systems):
    from app.core.copilot.scope import ScopeSnapshot

    novel = entities[0].novel if entities else Novel(id=1, title="test", language="zh")
    entities_by_id = {entity.id: entity for entity in entities}
    attrs_by_entity: dict[int, list] = {}
    for entity in entities:
        attrs = db.query(WorldEntityAttribute).filter(WorldEntityAttribute.entity_id == entity.id).all()
        if attrs:
            attrs_by_entity[entity.id] = attrs
    return ScopeSnapshot(
        novel=novel,
        novel_language="zh",
        entities=entities,
        entities_by_id=entities_by_id,
        relationships=relationships,
        systems=systems,
        attributes_by_entity=attrs_by_entity,
        draft_entities=[entity for entity in entities if entity.status == "draft"],
        draft_relationships=[relationship for relationship in relationships if relationship.status == "draft"],
        draft_systems=[system for system in systems if system.status == "draft"],
    )
