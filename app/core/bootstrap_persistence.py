# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.bootstrap_contract import (
    BOOTSTRAP_DRAFT_POLICY_REPLACE_BOOTSTRAP_DRAFTS,
    BOOTSTRAP_MODE_INDEX_REFRESH,
    BOOTSTRAP_MODE_REEXTRACT,
    LegacyDraftAmbiguity,
)
from app.core.bootstrap_refinement import BootstrapRefinementResult
from app.core.world.write import build_relationship_signature, relationship_signature_from_row
from app.language_policy import get_language_policy
from app.models import Novel, WorldEntity, WorldRelationship

LEGACY_ORIGIN_TRACKING_CUTOFF = datetime(2026, 2, 18, tzinfo=timezone.utc)


def _normalize_aliases(raw_aliases: Sequence[str], canonical_name: str) -> list[str]:
    policy = get_language_policy(sample_text=canonical_name)
    canonical = canonical_name.strip()
    canonical_key = policy.normalize_for_matching(canonical)
    seen_keys = {canonical_key}
    seen_raw = {canonical}
    aliases: list[str] = []
    for raw_alias in raw_aliases:
        alias = raw_alias.strip()
        if not alias or alias in seen_raw:
            continue
        key = policy.normalize_for_matching(alias)
        is_zh_surface_variant = (
            policy.base_language == "zh"
            and alias != canonical
            and key == canonical_key
        )
        if key in seen_keys and not is_zh_surface_variant:
            continue
        seen_raw.add(alias)
        if not is_zh_surface_variant:
            seen_keys.add(key)
        aliases.append(alias)
    return aliases


def _normalize_timestamp(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _is_legacy_manual_draft_row(
    *,
    created_at: datetime | None,
    updated_at: datetime | None,
    cutoff: datetime,
) -> bool:
    created = _normalize_timestamp(created_at)
    if created is None:
        return False

    normalized_cutoff = _normalize_timestamp(cutoff)
    if normalized_cutoff is None:
        return False

    if created >= normalized_cutoff:
        return False

    updated = _normalize_timestamp(updated_at)
    if updated is None:
        return True
    return updated <= normalized_cutoff


def find_legacy_manual_draft_ambiguity(
    db: Session,
    *,
    novel_id: int,
    cutoff: datetime = LEGACY_ORIGIN_TRACKING_CUTOFF,
) -> LegacyDraftAmbiguity:
    entity_ids = [
        row.id
        for row in db.query(
            WorldEntity.id,
            WorldEntity.created_at,
            WorldEntity.updated_at,
        )
        .filter(
            WorldEntity.novel_id == novel_id,
            WorldEntity.status == "draft",
            WorldEntity.origin == "manual",
        )
        .all()
        if _is_legacy_manual_draft_row(
            created_at=row.created_at,
            updated_at=row.updated_at,
            cutoff=cutoff,
        )
    ]

    relationship_ids = [
        row.id
        for row in db.query(
            WorldRelationship.id,
            WorldRelationship.created_at,
            WorldRelationship.updated_at,
        )
        .filter(
            WorldRelationship.novel_id == novel_id,
            WorldRelationship.status == "draft",
            WorldRelationship.origin == "manual",
        )
        .all()
        if _is_legacy_manual_draft_row(
            created_at=row.created_at,
            updated_at=row.updated_at,
            cutoff=cutoff,
        )
    ]

    return LegacyDraftAmbiguity(
        entity_ids=entity_ids,
        relationship_ids=relationship_ids,
    )


def _delete_bootstrap_origin_drafts(db: Session, *, novel_id: int) -> None:
    bootstrap_draft_entity_ids = [
        entity_id
        for (entity_id,) in db.query(WorldEntity.id)
        .filter(
            WorldEntity.novel_id == novel_id,
            WorldEntity.status == "draft",
            WorldEntity.origin == "bootstrap",
        )
        .all()
    ]

    db.query(WorldRelationship).filter(
        WorldRelationship.novel_id == novel_id,
        WorldRelationship.status == "draft",
        WorldRelationship.origin == "bootstrap",
    ).delete(synchronize_session=False)

    if not bootstrap_draft_entity_ids:
        return

    referenced_rows = (
        db.query(
            WorldRelationship.source_id,
            WorldRelationship.target_id,
        )
        .filter(
            WorldRelationship.novel_id == novel_id,
            or_(
                WorldRelationship.source_id.in_(bootstrap_draft_entity_ids),
                WorldRelationship.target_id.in_(bootstrap_draft_entity_ids),
            ),
        )
        .all()
    )
    referenced_entity_ids = {
        entity_id
        for row in referenced_rows
        for entity_id in row
        if entity_id in bootstrap_draft_entity_ids
    }
    deletable_entity_ids = [
        entity_id
        for entity_id in bootstrap_draft_entity_ids
        if entity_id not in referenced_entity_ids
    ]
    if deletable_entity_ids:
        db.query(WorldEntity).filter(WorldEntity.id.in_(deletable_entity_ids)).delete(
            synchronize_session=False
        )


def persist_bootstrap_output(
    db: Session,
    *,
    novel_id: int,
    refinement: BootstrapRefinementResult,
    mode: str,
    draft_policy: str | None,
) -> tuple[int, int]:
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if novel is None:
        raise ValueError(f"Novel not found: {novel_id}")

    if mode == BOOTSTRAP_MODE_INDEX_REFRESH:
        db.flush()
        return 0, 0

    if (
        mode == BOOTSTRAP_MODE_REEXTRACT
        and draft_policy == BOOTSTRAP_DRAFT_POLICY_REPLACE_BOOTSTRAP_DRAFTS
    ):
        _delete_bootstrap_origin_drafts(db, novel_id=novel_id)

    existing_entities = {
        entity.name: entity
        for entity in db.query(WorldEntity).filter(WorldEntity.novel_id == novel_id).all()
    }
    entities_written = 0
    new_entities: list[WorldEntity] = []

    for refined_entity in refinement.entities:
        name = refined_entity.name.strip()
        if not name:
            continue

        aliases = _normalize_aliases(refined_entity.aliases, name)
        entity_type = refined_entity.entity_type.strip() if refined_entity.entity_type else "other"
        if not entity_type:
            entity_type = "other"

        entity = existing_entities.get(name)
        if entity is None:
            entity = WorldEntity(
                novel_id=novel_id,
                name=name,
                entity_type=entity_type,
                aliases=aliases,
                origin="bootstrap",
                status="draft",
            )
            db.add(entity)
            new_entities.append(entity)
            existing_entities[name] = entity
            entities_written += 1
        elif entity.status == "draft" and entity.origin == "bootstrap":
            entity.entity_type = entity_type
            entity.aliases = _normalize_aliases([*(entity.aliases or []), *aliases], name)
            entities_written += 1

    if new_entities:
        # One flush assigns ids for relationship resolution below.
        db.flush()

    existing_relationship_keys = {
        relationship_signature_from_row(rel)
        for rel in db.query(WorldRelationship).filter(WorldRelationship.novel_id == novel_id).all()
    }
    relationships_written = 0

    for refined_relationship in refinement.relationships:
        source_name = refined_relationship.source_name.strip()
        target_name = refined_relationship.target_name.strip()
        label = refined_relationship.label.strip()
        if not source_name or not target_name or not label or source_name == target_name:
            continue

        source = existing_entities.get(source_name)
        target = existing_entities.get(target_name)
        if source is None or target is None:
            continue
        source_id = int(source.id)
        target_id = int(target.id)

        direct_key = build_relationship_signature(
            source_id=source_id,
            target_id=target_id,
            label=label,
        )
        reverse_key = build_relationship_signature(
            source_id=target_id,
            target_id=source_id,
            label_canonical=direct_key[2],
        )
        if direct_key in existing_relationship_keys or reverse_key in existing_relationship_keys:
            continue

        db.add(
            WorldRelationship(
                novel_id=novel_id,
                source_id=source_id,
                target_id=target_id,
                label=label,
                origin="bootstrap",
                status="draft",
            )
        )
        existing_relationship_keys.add(direct_key)
        relationships_written += 1

    db.flush()
    return entities_written, relationships_written


__all__ = [
    "LEGACY_ORIGIN_TRACKING_CUTOFF",
    "find_legacy_manual_draft_ambiguity",
    "persist_bootstrap_output",
]
