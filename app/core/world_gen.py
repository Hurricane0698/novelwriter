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
from app.core.world_write import build_relationship_signature, normalize_system_data_for_write
from app.config import get_settings
from app.models import WorldEntity, WorldRelationship, WorldSystem
from app.schemas import (
    WorldGenerateResponse,
    WorldGenerateWarning,
)
from app.core.text import PromptKey, get_prompt
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


def _chunk_world_generation_text(text: str) -> list[str]:
    settings = get_settings()
    normalized = (text or "").strip()
    if not normalized:
        return []

    chunk_chars = max(1, int(settings.world_generation_chunk_chars))
    max_chunks = max(1, int(settings.world_generation_max_chunks))
    overlap_chars = max(0, int(settings.world_generation_chunk_overlap_chars))
    overlap_chars = min(overlap_chars, chunk_chars - 1)

    if len(normalized) <= chunk_chars:
        return [normalized]

    step = max(1, chunk_chars - overlap_chars)
    chunks: list[str] = []
    start = 0
    while start < len(normalized) and len(chunks) < max_chunks:
        end = min(len(normalized), start + chunk_chars)
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start += step
    return chunks


def _build_world_generation_prompt(*, text: str, chunk_index: int, chunk_count: int) -> str:
    if chunk_count > 1:
        chunk_directive = (
            f"你当前只处理第{chunk_index}/{chunk_count}段设定文本。请尽量覆盖这一段中明确、稳定、可复用的设定。"
            "即使与其他段重复也没关系，系统稍后会自动去重整合；不要因为担心重复而把内容压缩得过少。"
        )
    else:
        chunk_directive = "请尽量完整覆盖文本中明确、稳定、可复用的设定，不要过度压缩条目数量。"
    return get_prompt(PromptKey.WORLD_GEN).format(text=text.strip(), chunk_directive=chunk_directive)


def _merge_worldgen_outputs(outputs: list[WorldGenLLMOutput]) -> WorldGenLLMOutput:
    entities: dict[str, WorldGenEntity] = {}
    relationships: dict[tuple[str, str, str], WorldGenRelationship] = {}
    systems: dict[str, WorldGenSystem] = {}

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

            merged_aliases = _norm_aliases(name=name, aliases=[*existing.aliases, *aliases])
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
            incoming_items = []
            seen_item_labels: set[str] = set()
            for item in sys.items or []:
                label = _norm(item.label)
                if not label or label in seen_item_labels:
                    continue
                seen_item_labels.add(label)
                incoming_items.append(WorldGenSystemItem(label=label, description=_norm(item.description) or None))
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
                    items=incoming_items,
                    constraints=incoming_constraints,
                )
                continue

            merged_items: dict[str, WorldGenSystemItem] = {item.label: item for item in existing.items or [] if _norm(item.label)}
            for item in incoming_items:
                prev = merged_items.get(item.label)
                if prev is None:
                    merged_items[item.label] = item
                else:
                    merged_items[item.label] = WorldGenSystemItem(
                        label=item.label,
                        description=_prefer_longer_text(prev.description or "", item.description or "") or None,
                    )
            merged_constraints: list[str] = []
            seen_merged_constraints: set[str] = set()
            for c in [*(existing.constraints or []), *incoming_constraints]:
                c = _norm(c)
                if not c or c in seen_merged_constraints:
                    continue
                seen_merged_constraints.add(c)
                merged_constraints.append(c)
            systems[name] = WorldGenSystem(
                name=name,
                description=_prefer_longer_text(existing.description, sys.description),
                items=list(merged_items.values()),
                constraints=merged_constraints,
            )

    return WorldGenLLMOutput(
        entities=list(entities.values()),
        relationships=list(relationships.values()),
        systems=list(systems.values()),
    )


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
    settings = get_settings()
    chunks = _chunk_world_generation_text(text)
    chunk_count = len(chunks)
    extracted_parts: list[WorldGenLLMOutput] = []

    for idx, chunk_text in enumerate(chunks, start=1):
        prompt = _build_world_generation_prompt(
            text=chunk_text,
            chunk_index=idx,
            chunk_count=chunk_count,
        )
        extracted_parts.append(
            await ai_client.generate_structured(
                prompt=prompt,
                response_model=WorldGenLLMOutput,
                system_prompt=get_prompt(PromptKey.WORLD_GEN_SYSTEM),
                # Structured extraction — low temperature for schema adherence.
                temperature=0.3,
                max_tokens=settings.world_generation_chunk_max_tokens,
                user_id=user_id,
                **llm_kwargs,
            )
        )

    if len(extracted_parts) <= 1:
        extracted = extracted_parts[0] if extracted_parts else WorldGenLLMOutput()
    else:
        extracted = _merge_worldgen_outputs(extracted_parts)

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
            signature = build_relationship_signature(
                source_id=int(src_id),
                target_id=int(tgt_id),
                label_canonical=str(label_canonical or ""),
            )
            if not signature[2]:
                continue
            relationship_keys_seen.add(signature)

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

            rel_key = build_relationship_signature(
                source_id=int(src_id),
                target_id=int(tgt_id),
                label=label,
            )
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
            data = normalize_system_data_for_write("list", data)

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
