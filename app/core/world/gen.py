# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""World generation: free-text world settings -> draft World Model rows.

This is intentionally draft-only. Users must review/confirm via existing UI.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.ai_client import ai_client
from app.core.world.write import build_relationship_signature, normalize_system_data_for_write
from app.config import get_settings
from app.language import resolve_prompt_locale
from app.models import Novel, WorldEntity, WorldRelationship, WorldSystem
from app.schemas import (
    WorldGenerateResponse,
    WorldGenerateWarning,
)
from app.core.text import PromptKey, get_prompt
from app.core.text.snippets import SnippetKey, get_snippet

logger = logging.getLogger(__name__)

WORLDGEN_ORIGIN = "worldgen"
WorldGenSystemDisplayType = Literal["list", "hierarchy", "timeline"]


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
    time: str | None = None
    children: list["WorldGenSystemItem"] = Field(default_factory=list)


WorldGenSystemItem.model_rebuild()


class WorldGenSystem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    display_type: WorldGenSystemDisplayType = "list"
    items: list[WorldGenSystemItem] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)

    @field_validator("display_type", mode="before")
    @classmethod
    def _normalize_display_type(cls, value: object) -> object:
        return _normalize_worldgen_system_display_type(cast(str | None, value))


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


def _normalize_worldgen_system_display_type(display_type: str | None) -> WorldGenSystemDisplayType:
    normalized = _norm(display_type).lower()
    if normalized in {"list", "hierarchy", "timeline"}:
        return cast(WorldGenSystemDisplayType, normalized)
    return "list"


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


def _normalize_worldgen_system_item(item: WorldGenSystemItem) -> WorldGenSystemItem | None:
    label = _norm(item.label)
    if not label:
        return None
    return WorldGenSystemItem(
        label=label,
        description=_norm(item.description) or None,
        time=_norm(item.time) or None,
        children=_merge_worldgen_system_items(list(item.children or []), display_type="hierarchy"),
    )


def _merge_worldgen_system_item(current: WorldGenSystemItem, candidate: WorldGenSystemItem) -> WorldGenSystemItem:
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
            {"nodes": _build_worldgen_hierarchy_nodes(system_name=system.name, items=list(system.items or []))}
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


def _build_world_generation_prompt(
    *,
    text: str,
    chunk_index: int,
    chunk_count: int,
    prompt_locale: str,
) -> str:
    if chunk_count > 1:
        chunk_directive = get_snippet(
            SnippetKey.WORLDGEN_CHUNK_DIRECTIVE_MULTI, prompt_locale,
        ).format(chunk_index=chunk_index, chunk_count=chunk_count)
    else:
        chunk_directive = get_snippet(
            SnippetKey.WORLDGEN_CHUNK_DIRECTIVE_SINGLE, prompt_locale,
        )
    return get_prompt(PromptKey.WORLD_GEN, locale=prompt_locale).format(
        text=text.strip(),
        chunk_directive=chunk_directive,
    )


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
            incoming_display_type = _normalize_worldgen_system_display_type(sys.display_type)
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

            existing_display_type = _normalize_worldgen_system_display_type(existing.display_type)
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

            if existing_display_type != incoming_display_type and name not in warned_system_display_type_conflicts:
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
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    prompt_locale = resolve_prompt_locale(novel_language=getattr(novel, "language", None))
    chunks = _chunk_world_generation_text(text)
    chunk_count = len(chunks)
    extracted_parts: list[WorldGenLLMOutput] = []

    for idx, chunk_text in enumerate(chunks, start=1):
        prompt = _build_world_generation_prompt(
            text=chunk_text,
            chunk_index=idx,
            chunk_count=chunk_count,
            prompt_locale=prompt_locale,
        )
        extracted_parts.append(
            await ai_client.generate_structured(
                prompt=prompt,
                response_model=WorldGenLLMOutput,
                system_prompt=get_prompt(PromptKey.WORLD_GEN_SYSTEM, locale=prompt_locale),
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
        extracted = _merge_worldgen_outputs(extracted_parts, warnings=warnings)

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

        entities_created = 0
        relationships_created = 0
        systems_created = 0

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
            entities_created += 1

        if new_entities:
            db.flush()
            for entity in new_entities:
                name_to_entity_id[str(entity.name)] = int(entity.id)

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
                        display_type=_normalize_worldgen_system_display_type(sys.display_type),
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
