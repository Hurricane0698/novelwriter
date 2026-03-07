# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""
Context Assembly — visibility-driven prompt injection for WorldModel.

Implements the "Prompt Assembly Visibility Contract" from:
  .trellis/spec/backend/context-assembly.md

Primary callers:
- /api/novels/{novel_id}/continue (writer context)
- future consistency checker (checker context)

This module is intentionally DB-read-only.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import json
import logging
from typing import Any, Dict, Iterable, Mapping, Sequence, Set

import ahocorasick
from sqlalchemy.orm import Session, joinedload

from app.models import WorldEntity, WorldRelationship, WorldSystem
from app.world_visibility import VIS_ACTIVE, VIS_HIDDEN, VIS_REFERENCE

logger = logging.getLogger(__name__)

DEFAULT_WORLD_CONTEXT_TOKEN_BUDGET = 100_000


@dataclass(frozen=True)
class _SpanMatch:
    start: int
    end: int  # exclusive
    entity_id: int
    keyword: str


@dataclass
class _EntityMatchAgg:
    """Aggregated match info for sorting + debug."""

    terms: Set[str]
    count: int = 0


def _iter_entity_keywords(entity: WorldEntity) -> Iterable[str]:
    yield (entity.name or "").strip()
    aliases = getattr(entity, "aliases", None) or []
    for alias in aliases:
        yield (alias or "").strip()


def _build_keyword_index(
    entities: Sequence[WorldEntity],
) -> tuple[dict[str, int], set[str]]:
    """
    Build keyword -> entity_id mapping for relevance detection.

    Returns:
      - keyword_to_entity_id: only unambiguous keywords (unique mapping)
      - ambiguous_keywords: keywords mapping to multiple entities (disabled triggers)
    """
    keyword_to_ids: dict[str, set[int]] = {}
    for entity in entities:
        for keyword in _iter_entity_keywords(entity):
            if not keyword:
                continue
            keyword_to_ids.setdefault(keyword, set()).add(int(entity.id))

    ambiguous_keywords = {k for k, ids in keyword_to_ids.items() if len(ids) > 1}
    keyword_to_entity_id: dict[str, int] = {}
    for keyword, ids in keyword_to_ids.items():
        if keyword in ambiguous_keywords:
            continue
        # Unambiguous by construction.
        keyword_to_entity_id[keyword] = next(iter(ids))
    return keyword_to_entity_id, ambiguous_keywords


def _find_relevant_entities(
    db: Session,
    novel_id: int,
    chapter_text: str,
) -> tuple[Set[int], Mapping[int, _EntityMatchAgg], Set[str]]:
    """
    Relevance detection via Aho-Corasick scan over confirmed entity names/aliases.

    Noise rules (MVP):
    - ambiguous alias/name (keyword maps to multiple entities) does not trigger
    - longest match priority: drop matches fully contained within a longer match span
    """
    text = chapter_text or ""

    confirmed_entities = (
        db.query(WorldEntity)
        .filter(WorldEntity.novel_id == novel_id, WorldEntity.status == "confirmed")
        .all()
    )
    if not confirmed_entities or not text.strip():
        return set(), {}, set()

    keyword_to_entity_id, ambiguous_keywords = _build_keyword_index(confirmed_entities)
    if not keyword_to_entity_id:
        return set(), {}, ambiguous_keywords

    automaton = ahocorasick.Automaton()
    for keyword, entity_id in keyword_to_entity_id.items():
        # Store keyword to recover span length and debug term.
        automaton.add_word(keyword, (int(entity_id), keyword))
    automaton.make_automaton()

    matches: list[_SpanMatch] = []
    for end_idx, (entity_id, keyword) in automaton.iter(text):
        start = end_idx - len(keyword) + 1
        if start < 0:
            continue
        matches.append(_SpanMatch(start=start, end=end_idx + 1, entity_id=entity_id, keyword=keyword))

    if not matches:
        return set(), {}, ambiguous_keywords

    # Deduplicate identical spans (can happen when data contains duplicate aliases).
    deduped: dict[tuple[int, int, int], _SpanMatch] = {}
    for m in matches:
        deduped[(m.start, m.end, m.entity_id)] = m
    matches = list(deduped.values())

    # Longest-match priority: drop any match span fully contained in a previously
    # kept match with an earlier (or equal) start and later (or equal) end.
    # Sorting by (start asc, end desc) ensures containers are seen first.
    matches.sort(key=lambda m: (m.start, -(m.end - m.start), -m.end, m.entity_id))
    kept: list[_SpanMatch] = []
    max_end = -1
    for m in matches:
        if m.end <= max_end:
            continue
        kept.append(m)
        max_end = m.end

    relevant_ids: set[int] = set()
    agg: dict[int, _EntityMatchAgg] = {}
    for m in kept:
        relevant_ids.add(int(m.entity_id))
        bucket = agg.get(int(m.entity_id))
        if bucket is None:
            bucket = _EntityMatchAgg(terms=set(), count=0)
            agg[int(m.entity_id)] = bucket
        bucket.count += 1
        bucket.terms.add(m.keyword)

    return relevant_ids, agg, ambiguous_keywords


def _filter_system_data_for_writer(display_type: str, data: Any) -> Any:
    """Filter per-element visibility inside WorldSystem.data for writer context."""
    if not isinstance(data, dict):
        return data

    def keep(vis: str | None) -> bool:
        if not vis:
            return True
        return vis != VIS_HIDDEN

    if display_type == "hierarchy":
        nodes = data.get("nodes")
        if not isinstance(nodes, list):
            return data

        def filter_node(node: Any) -> Any | None:
            if not isinstance(node, dict):
                return None
            if not keep(node.get("visibility")):
                return None
            children = node.get("children")
            if isinstance(children, list):
                filtered_children = [c for c in (filter_node(x) for x in children) if c is not None]
                node = {**node, "children": filtered_children}
            return node

        filtered = [n for n in (filter_node(x) for x in nodes) if n is not None]
        return {**data, "nodes": filtered}

    if display_type == "graph":
        nodes = data.get("nodes")
        edges = data.get("edges")
        out = dict(data)
        if isinstance(nodes, list):
            out["nodes"] = [n for n in nodes if isinstance(n, dict) and keep(n.get("visibility"))]
        if isinstance(edges, list):
            out["edges"] = [e for e in edges if isinstance(e, dict) and keep(e.get("visibility"))]
        return out

    if display_type == "timeline":
        events = data.get("events")
        if isinstance(events, list):
            return {**data, "events": [e for e in events if isinstance(e, dict) and keep(e.get("visibility"))]}
        return data

    if display_type == "list":
        items = data.get("items")
        if isinstance(items, list):
            return {**data, "items": [i for i in items if isinstance(i, dict) and keep(i.get("visibility"))]}
        return data

    return data


def _estimate_writer_context_tokens(writer_ctx: Mapping[str, Any]) -> int:
    """
    Rough token estimator for writer prompt injection.

    We intentionally use a cheap, deterministic character-count heuristic instead of
    a tokenizer. The budget is a safety fuse (100k) and doesn't need precision.
    """

    def s(value: Any) -> str:
        return str(value) if value is not None else ""

    total = 0
    systems = writer_ctx.get("systems") or []
    if isinstance(systems, list):
        for sys in systems:
            if not isinstance(sys, dict):
                continue
            total += len(s(sys.get("name")))
            total += len(s(sys.get("display_type")))
            total += len(s(sys.get("description")))
            constraints = sys.get("constraints") or []
            if isinstance(constraints, list):
                for c in constraints:
                    total += len(s(c))
            data = sys.get("data")
            if data is not None:
                try:
                    total += len(json.dumps(data, ensure_ascii=False, sort_keys=True))
                except TypeError:
                    total += len(s(data))

    entities = writer_ctx.get("entities") or []
    if isinstance(entities, list):
        for ent in entities:
            if not isinstance(ent, dict):
                continue
            total += len(s(ent.get("name")))
            aliases = ent.get("aliases") or []
            if isinstance(aliases, list):
                for a in aliases:
                    total += len(s(a))
            total += len(s(ent.get("entity_type")))
            total += len(s(ent.get("description")))
            attrs = ent.get("attributes") or []
            if isinstance(attrs, list):
                for attr in attrs:
                    if not isinstance(attr, dict):
                        continue
                    total += len(s(attr.get("key")))
                    total += len(s(attr.get("surface")))

    rels = writer_ctx.get("relationships") or []
    if isinstance(rels, list):
        for rel in rels:
            if not isinstance(rel, dict):
                continue
            total += len(s(rel.get("label")))
            total += len(s(rel.get("description")))

    return total


def apply_writer_context_budget(
    writer_ctx: Mapping[str, Any],
    *,
    max_estimated_tokens: int = DEFAULT_WORLD_CONTEXT_TOKEN_BUDGET,
) -> Dict[str, Any]:
    """
    Enforce a hard budget on writer context injection.

    Truncation order (deterministic, testable):
      1) drop reference relationships
      2) drop reference attributes
      3) drop tail entities (and any relationships connected to them)

    The budget uses a rough token estimate (character-count heuristic).
    """
    if max_estimated_tokens <= 0:
        raise ValueError("max_estimated_tokens must be > 0")

    ctx: Dict[str, Any] = copy.deepcopy(dict(writer_ctx))
    ctx.setdefault("systems", [])
    ctx.setdefault("entities", [])
    ctx.setdefault("relationships", [])

    if _estimate_writer_context_tokens(ctx) <= max_estimated_tokens:
        return ctx

    # 1) Drop reference relationships.
    rels = ctx.get("relationships")
    if isinstance(rels, list):
        ctx["relationships"] = [r for r in rels if isinstance(r, dict) and (r.get("visibility") != VIS_REFERENCE)]

    if _estimate_writer_context_tokens(ctx) <= max_estimated_tokens:
        return ctx

    # 2) Drop reference attributes (keep active only).
    entities = ctx.get("entities")
    if isinstance(entities, list):
        for ent in entities:
            if not isinstance(ent, dict):
                continue
            attrs = ent.get("attributes")
            if not isinstance(attrs, list):
                continue
            ent["attributes"] = [
                a
                for a in attrs
                if isinstance(a, dict) and (a.get("visibility") != VIS_REFERENCE)
            ]

    if _estimate_writer_context_tokens(ctx) <= max_estimated_tokens:
        return ctx

    # 3) Drop tail entities until within budget; also remove dangling relationships.
    if isinstance(entities, list):
        while entities and _estimate_writer_context_tokens(ctx) > max_estimated_tokens:
            dropped = entities.pop()
            dropped_id = dropped.get("id") if isinstance(dropped, dict) else None
            try:
                dropped_id_int = int(dropped_id) if dropped_id is not None else None
            except Exception:
                dropped_id_int = None

            rels = ctx.get("relationships")
            if dropped_id_int is not None and isinstance(rels, list):
                kept_rels: list[dict[str, Any]] = []
                for r in rels:
                    if not isinstance(r, dict):
                        continue
                    try:
                        src = int(r.get("source_id"))
                        tgt = int(r.get("target_id"))
                    except Exception:
                        kept_rels.append(r)
                        continue
                    if src == dropped_id_int or tgt == dropped_id_int:
                        continue
                    kept_rels.append(r)
                ctx["relationships"] = kept_rels

    return ctx


def assemble_writer_context(db: Session, novel_id: int, chapter_text: str) -> Dict[str, Any]:
    """
    Assemble writer-facing context: confirmed + visible, relevance-gated.

    Visibility rules:
    - active: included by default (for attributes/relationships within relevant entities)
    - reference: included only when directly relevant (same as entity relevance in MVP)
    - hidden: never included
    """
    relevant_ids, agg, ambiguous_keywords = _find_relevant_entities(db, novel_id, chapter_text)

    entities_out: list[dict[str, Any]] = []
    if relevant_ids:
        entities = (
            db.query(WorldEntity)
            .options(joinedload(WorldEntity.attributes))
            .filter(
                WorldEntity.novel_id == novel_id,
                WorldEntity.status == "confirmed",
                WorldEntity.id.in_(sorted(relevant_ids)),
            )
            .all()
        )

        entities.sort(key=lambda e: (-agg.get(int(e.id), _EntityMatchAgg(set(), 0)).count, e.name))
        for entity in entities:
            attrs = []
            for attr in sorted(entity.attributes, key=lambda a: (a.sort_order, a.key)):
                if attr.visibility == VIS_HIDDEN:
                    continue
                attrs.append(
                    {
                        "id": int(attr.id),
                        "key": attr.key,
                        "surface": attr.surface,
                        "visibility": attr.visibility,
                        "sort_order": int(attr.sort_order or 0),
                    }
                )

            entities_out.append(
                {
                    "id": int(entity.id),
                    "name": entity.name,
                    "aliases": list(entity.aliases or []),
                    "entity_type": entity.entity_type,
                    "description": entity.description or "",
                    "attributes": attrs,
                    "match_count": agg.get(int(entity.id), _EntityMatchAgg(set(), 0)).count,
                    "matched_terms": sorted(agg.get(int(entity.id), _EntityMatchAgg(set(), 0)).terms),
                }
            )

    # Relationships: only between selected (relevant) entities.
    relationships_out: list[dict[str, Any]] = []
    if relevant_ids:
        rels = (
            db.query(WorldRelationship)
            .filter(
                WorldRelationship.novel_id == novel_id,
                WorldRelationship.status == "confirmed",
                WorldRelationship.source_id.in_(sorted(relevant_ids)),
                WorldRelationship.target_id.in_(sorted(relevant_ids)),
            )
            .all()
        )
        for rel in rels:
            if rel.visibility == VIS_HIDDEN:
                continue
            relationships_out.append(
                {
                    "id": int(rel.id),
                    "source_id": int(rel.source_id),
                    "target_id": int(rel.target_id),
                    "label": rel.label,
                    "description": rel.description or "",
                    "visibility": rel.visibility,
                }
            )

        relationships_out.sort(key=lambda r: (r["source_id"], r["target_id"], r["label"]))

    # Systems: confirmed + visibility=active are always injected for writer.
    systems_out: list[dict[str, Any]] = []
    systems = (
        db.query(WorldSystem)
        .filter(
            WorldSystem.novel_id == novel_id,
            WorldSystem.status == "confirmed",
            WorldSystem.visibility == VIS_ACTIVE,
        )
        .all()
    )
    systems.sort(key=lambda s: s.name)
    for system in systems:
        systems_out.append(
            {
                "id": int(system.id),
                "name": system.name,
                "display_type": system.display_type,
                "description": system.description or "",
                "data": _filter_system_data_for_writer(system.display_type, system.data),
                "constraints": list(system.constraints or []),
                "visibility": system.visibility,
                "status": system.status,
            }
        )

    return {
        "entities": entities_out,
        "relationships": relationships_out,
        "systems": systems_out,
        "debug": {
            "relevant_entity_ids": sorted(relevant_ids),
            "ambiguous_keywords_disabled": sorted(ambiguous_keywords),
        },
    }


def assemble_checker_context(db: Session, novel_id: int, chapter_text: str) -> Dict[str, Any]:
    """
    Assemble checker-facing context: same relevance gating, but includes hidden + truth.

    Used for consistency checks (future). Must remain DB-read-only.
    """
    relevant_ids, agg, ambiguous_keywords = _find_relevant_entities(db, novel_id, chapter_text)

    entities_out: list[dict[str, Any]] = []
    if relevant_ids:
        entities = (
            db.query(WorldEntity)
            .options(joinedload(WorldEntity.attributes))
            .filter(
                WorldEntity.novel_id == novel_id,
                WorldEntity.status == "confirmed",
                WorldEntity.id.in_(sorted(relevant_ids)),
            )
            .all()
        )
        entities.sort(key=lambda e: (-agg.get(int(e.id), _EntityMatchAgg(set(), 0)).count, e.name))
        for entity in entities:
            attrs = []
            for attr in sorted(entity.attributes, key=lambda a: (a.sort_order, a.key)):
                attrs.append(
                    {
                        "id": int(attr.id),
                        "key": attr.key,
                        "surface": attr.surface,
                        "truth": attr.truth,
                        "visibility": attr.visibility,
                        "sort_order": int(attr.sort_order or 0),
                    }
                )

            entities_out.append(
                {
                    "id": int(entity.id),
                    "name": entity.name,
                    "aliases": list(entity.aliases or []),
                    "entity_type": entity.entity_type,
                    "description": entity.description or "",
                    "attributes": attrs,
                    "match_count": agg.get(int(entity.id), _EntityMatchAgg(set(), 0)).count,
                    "matched_terms": sorted(agg.get(int(entity.id), _EntityMatchAgg(set(), 0)).terms),
                }
            )

    relationships_out: list[dict[str, Any]] = []
    if relevant_ids:
        rels = (
            db.query(WorldRelationship)
            .filter(
                WorldRelationship.novel_id == novel_id,
                WorldRelationship.status == "confirmed",
                WorldRelationship.source_id.in_(sorted(relevant_ids)),
                WorldRelationship.target_id.in_(sorted(relevant_ids)),
            )
            .all()
        )
        for rel in rels:
            relationships_out.append(
                {
                    "id": int(rel.id),
                    "source_id": int(rel.source_id),
                    "target_id": int(rel.target_id),
                    "label": rel.label,
                    "description": rel.description or "",
                    "visibility": rel.visibility,
                }
            )

        relationships_out.sort(key=lambda r: (r["source_id"], r["target_id"], r["label"]))

    # Checker sees all confirmed systems (including hidden), unfiltered.
    systems_out: list[dict[str, Any]] = []
    systems = (
        db.query(WorldSystem)
        .filter(
            WorldSystem.novel_id == novel_id,
            WorldSystem.status == "confirmed",
        )
        .all()
    )
    systems.sort(key=lambda s: s.name)
    for system in systems:
        systems_out.append(
            {
                "id": int(system.id),
                "name": system.name,
                "display_type": system.display_type,
                "description": system.description or "",
                "data": system.data,
                "constraints": list(system.constraints or []),
                "visibility": system.visibility,
                "status": system.status,
            }
        )

    return {
        "entities": entities_out,
        "relationships": relationships_out,
        "systems": systems_out,
        "debug": {
            "relevant_entity_ids": sorted(relevant_ids),
            "ambiguous_keywords_disabled": sorted(ambiguous_keywords),
        },
    }
