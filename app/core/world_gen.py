# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""World generation: free-text world settings -> draft World Model rows.

This is intentionally draft-only. Users must review/confirm via existing UI.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.ai_client import ai_client
from app.models import WorldEntity, WorldRelationship, WorldSystem
from app.schemas import (
    WorldGenerateResponse,
    WorldGenerateWarning,
    _normalize_and_validate_system_data,
)
from app.utils.prompts import WORLD_GENERATION_PROMPT, WORLD_GENERATION_SYSTEM_PROMPT
from app.world_relationships import canonicalize_relationship_label

logger = logging.getLogger(__name__)

WORLDGEN_ORIGIN = "worldgen"


class WorldGenEntity(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=255)
    entity_type: str = Field(min_length=1, max_length=50)
    description: str = ""
    aliases: list[str] = Field(default_factory=list)


class WorldGenRelationship(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source: str = Field(min_length=1, max_length=255)
    target: str = Field(min_length=1, max_length=255)
    label: str = Field(min_length=1, max_length=100)
    description: str = ""


class WorldGenSystemItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    label: str = Field(min_length=1, max_length=255)
    description: str | None = None


class WorldGenSystem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    items: list[WorldGenSystemItem] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class WorldGenLLMOutput(BaseModel):
    """Intermediate schema: LLM extracts content only; server fills metadata/defaults."""

    model_config = ConfigDict(extra="ignore")

    entities: list[WorldGenEntity] = Field(default_factory=list)
    relationships: list[WorldGenRelationship] = Field(default_factory=list)
    systems: list[WorldGenSystem] = Field(default_factory=list)


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
        try:
            protected_entity_ids.add(int(src_id))
            protected_entity_ids.add(int(tgt_id))
        except Exception:
            continue

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


async def generate_world_drafts(
    *,
    db: Session,
    novel_id: int,
    text: str,
    llm_config: dict | None = None,
    user_id: int | None = None,
) -> WorldGenerateResponse:
    """Generate and persist draft world items from free text.

    Notes:
    - Deletes previous world generation drafts (origin=worldgen,status=draft) before inserting new ones.
    - Confirmed/manual rows are preserved.
    """

    warnings: list[WorldGenerateWarning] = []

    llm_kwargs = llm_config or {}
    prompt = WORLD_GENERATION_PROMPT.format(text=text.strip())

    extracted = await ai_client.generate_structured(
        prompt=prompt,
        response_model=WorldGenLLMOutput,
        system_prompt=WORLD_GENERATION_SYSTEM_PROMPT,
        # Structured extraction — low temperature for schema adherence.
        temperature=0.3,
        max_tokens=8000,
        user_id=user_id,
        **llm_kwargs,
    )

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

        name_to_system_id: dict[str, int] = {}
        for system_id, name in (
            db.query(WorldSystem.id, WorldSystem.name)
            .filter(WorldSystem.novel_id == novel_id)
            .all()
        ):
            if name:
                name_to_system_id[str(name)] = int(system_id)
        existing_system_names = set(name_to_system_id.keys())

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
            lc = _norm(str(label_canonical or ""))
            if not lc:
                continue
            relationship_keys_seen.add((int(src_id), int(tgt_id), lc))

        entities_created = 0
        relationships_created = 0
        systems_created = 0

        # Entities
        for idx, ent in enumerate(extracted.entities or []):
            name = _norm(ent.name)
            if not name:
                warnings.append(
                    WorldGenerateWarning(
                        code="entity_skipped",
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
            db.flush()  # assign id for relationship resolution
            name_to_entity_id[name] = int(entity.id)
            entities_created += 1

        # Relationships
        for idx, rel in enumerate(extracted.relationships or []):
            src_name = _norm(rel.source)
            tgt_name = _norm(rel.target)
            label = _norm(rel.label)
            if not src_name or not tgt_name or not label:
                warnings.append(
                    WorldGenerateWarning(
                        code="relationship_skipped",
                        message="Relationship missing source/target/label; skipped",
                        path=f"relationships[{idx}]",
                    )
                )
                continue

            src_id = name_to_entity_id.get(src_name)
            tgt_id = name_to_entity_id.get(tgt_name)
            if not src_id or not tgt_id:
                warnings.append(
                    WorldGenerateWarning(
                        code="orphan_relationship_dropped",
                        message="Relationship references unknown entity; dropped",
                        path=f"relationships[{idx}]",
                    )
                )
                continue

            if int(src_id) == int(tgt_id):
                warnings.append(
                    WorldGenerateWarning(
                        code="relationship_skipped",
                        message="Relationship source and target are identical; skipped",
                        path=f"relationships[{idx}]",
                    )
                )
                continue

            label_canonical = canonicalize_relationship_label(label)
            rel_key = (int(src_id), int(tgt_id), label_canonical)
            if rel_key in relationship_keys_seen:
                warnings.append(
                    WorldGenerateWarning(
                        code="relationship_duplicate_dropped",
                        message="Duplicate relationship; dropped",
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

        # Systems (default display_type=list, visibility=reference)
        seen_system_names: set[str] = set()
        for idx, sys in enumerate(extracted.systems or []):
            name = _norm(sys.name)
            if not name:
                warnings.append(
                    WorldGenerateWarning(
                        code="system_skipped",
                        message="System name is empty; skipped",
                        path=f"systems[{idx}].name",
                    )
                )
                continue
            if name in seen_system_names:
                warnings.append(
                    WorldGenerateWarning(
                        code="system_duplicate_dropped",
                        message="Duplicate system name; dropped",
                        path=f"systems[{idx}].name",
                    )
                )
                continue
            seen_system_names.add(name)

            if name in existing_system_names:
                warnings.append(
                    WorldGenerateWarning(
                        code="system_conflict_skipped",
                        message="System name already exists; skipped",
                        path=f"systems[{idx}].name",
                    )
                )
                continue

            items_payload = []
            seen_item_labels: set[str] = set()
            for item in sys.items or []:
                label = _norm(item.label)
                if not label:
                    continue
                if label in seen_item_labels:
                    continue
                seen_item_labels.add(label)
                items_payload.append(
                    {
                        "label": label,
                        "description": _norm(item.description),
                        "visibility": "reference",
                    }
                )
            data = {"items": items_payload} if items_payload else {}
            data = _normalize_and_validate_system_data("list", data)

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
                display_type="list",
                description=_norm(sys.description),
                data=data,
                constraints=constraints,
                visibility="reference",
                origin=WORLDGEN_ORIGIN,
                status="draft",
            )
            db.add(system)
            db.flush()
            name_to_system_id[name] = int(system.id)
            systems_created += 1

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
        logger.warning("world_gen: persist conflict for novel %s", novel_id, exc_info=True)
        raise
    except Exception:
        db.rollback()
        logger.exception("world_gen: persist failed for novel %s", novel_id)
        raise
