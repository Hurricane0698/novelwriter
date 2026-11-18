# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Select confirmed world details for a continuation scene."""

from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
from typing import Any, Iterable, Mapping, Sequence

import ahocorasick
from sqlalchemy.orm import Session, joinedload, load_only

from app.core.continuation_text import extract_narrative_constraints, format_world_context_for_prompt
from app.core.indexing.builder import get_tokenizer, load_common_words
from app.language_policy import LanguagePolicy, get_language_policy
from app.models import Novel, WorldEntity, WorldRelationship, WorldSystem
from app.world_visibility import VIS_ACTIVE, VIS_HIDDEN

WORLD_CONTEXT_MAX_CHARS = 12_000


@dataclass(frozen=True)
class _SpanMatch:
    start: int
    end: int  # exclusive
    entity_id: int
    keyword: str


@dataclass
class _EntityMatchAgg:
    terms: set[str]
    count: int = 0


def _iter_entity_keywords(entity: WorldEntity) -> Iterable[str]:
    yield (entity.name or "").strip()
    aliases = getattr(entity, "aliases", None) or []
    for alias in aliases:
        yield (alias or "").strip()


def _build_keyword_index(
    entities: Sequence[WorldEntity],
    *,
    policy: LanguagePolicy,
) -> tuple[dict[str, int], set[str], dict[str, str]]:
    """
    Build keyword -> entity_id mapping for relevance detection.

    Returns:
      - keyword_to_entity_id: only unambiguous keywords (unique mapping)
      - ambiguous_keywords: keywords mapping to multiple entities (disabled triggers)
      - keyword_display: normalized keyword -> representative display term
    """
    keyword_to_ids: dict[str, set[int]] = {}
    keyword_display_terms: dict[str, set[str]] = {}
    for entity in entities:
        for keyword in _iter_entity_keywords(entity):
            raw_keyword = keyword.strip()
            if not raw_keyword:
                continue
            normalized_keyword = policy.normalize_for_matching(raw_keyword)
            if not normalized_keyword:
                continue
            keyword_to_ids.setdefault(normalized_keyword, set()).add(int(entity.id))
            keyword_display_terms.setdefault(normalized_keyword, set()).add(raw_keyword)

    ambiguous_keywords = {k for k, ids in keyword_to_ids.items() if len(ids) > 1}
    keyword_to_entity_id: dict[str, int] = {}
    for keyword, ids in keyword_to_ids.items():
        if keyword in ambiguous_keywords:
            continue
        # Unambiguous by construction.
        keyword_to_entity_id[keyword] = next(iter(ids))
    keyword_display = {
        keyword: sorted(keyword_display_terms.get(keyword, {keyword}), key=lambda value: (len(value), value))[0]
        for keyword in keyword_to_entity_id
    }
    ambiguous_display_terms = {
        term
        for keyword in ambiguous_keywords
        for term in keyword_display_terms.get(keyword, set())
    }
    return keyword_to_entity_id, ambiguous_display_terms, keyword_display


def _find_relevant_entities(
    entities: Sequence[WorldEntity], policy: LanguagePolicy, text: str,
) -> tuple[dict[int, _EntityMatchAgg], set[str]]:
    keyword_to_entity_id, ambiguous_keywords, keyword_display = _build_keyword_index(
        entities,
        policy=policy,
    )
    if not keyword_to_entity_id:
        return {}, ambiguous_keywords

    automaton = ahocorasick.Automaton()
    for keyword, entity_id in keyword_to_entity_id.items():
        # Store keyword to recover span length and debug term.
        automaton.add_word(keyword, (int(entity_id), keyword, keyword_display.get(keyword, keyword)))
    automaton.make_automaton()

    matches: list[_SpanMatch] = []
    for end_idx, (entity_id, keyword, display_keyword) in automaton.iter(text):
        start = end_idx - len(keyword) + 1
        if start < 0:
            continue
        if not policy.match_has_word_boundaries(text, start, end_idx + 1):
            continue
        matches.append(_SpanMatch(start=start, end=end_idx + 1, entity_id=entity_id, keyword=display_keyword))

    # Ignore short aliases contained inside a longer name at the same position.
    matches.sort(key=lambda m: (m.start, -(m.end - m.start), -m.end, m.entity_id))
    kept: list[_SpanMatch] = []
    max_end = -1
    for m in matches:
        if m.end <= max_end:
            continue
        kept.append(m)
        max_end = m.end

    agg: dict[int, _EntityMatchAgg] = {}
    for m in kept:
        bucket = agg.get(int(m.entity_id))
        if bucket is None:
            bucket = _EntityMatchAgg(terms=set(), count=0)
            agg[int(m.entity_id)] = bucket
        bucket.count += 1
        bucket.terms.add(m.keyword)

    return agg, ambiguous_keywords


def _scene_system_data(system, includes, relevant_ids, *, whole):
    """Keep matching entries and their ancestors; hidden branches never enter the prompt."""
    key = {"hierarchy": "nodes", "timeline": "events", "list": "items", "graph": "nodes"}.get(system.display_type)
    if not key:
        return {}

    def select(entries):
        selected = []
        for entry in entries:
            if entry.get("visibility") == VIS_HIDDEN:
                continue
            children = select(entry.get("children") or [])
            if whole or children or entry.get("entity_id") in relevant_ids or includes(entry.get("label", "")):
                selected.append({**entry, **({"children": children} if "children" in entry else {})})
        return selected

    data = system.data or {}
    entries = select(data.get(key, []))
    if system.display_type == "graph":
        node_ids = {node.get("id") for node in entries}
        edges = [edge for edge in data.get("edges", []) if edge.get("visibility") != VIS_HIDDEN
                 and edge.get("from") in node_ids and edge.get("to") in node_ids]
        return {"nodes": entries, "edges": edges}
    return {key: entries}


def apply_writer_context_budget(
    writer_ctx: Mapping[str, Any], *, max_chars: int = WORLD_CONTEXT_MAX_CHARS, locale: str | None = None,
) -> dict[str, Any]:
    """Limit the rendered world material, including its separate narrative rules section."""
    def size(ctx):
        return len(format_world_context_for_prompt(ctx, locale=locale)) + len(extract_narrative_constraints(ctx))

    if size(writer_ctx) <= max_chars:
        return dict(writer_ctx)

    result = {**writer_ctx, "entities": [], "relationships": [], "systems": []}
    remaining = max_chars
    names = {}

    def add(kind, item):
        nonlocal remaining
        # Counting the section heading per item slightly underfills an overflowing prompt.
        cost = len(format_world_context_for_prompt({kind: [item]}, locale=locale, entity_names=names)) + 1
        if cost > remaining:
            return False
        remaining -= cost
        result[kind].append(item)
        return True

    for entity in writer_ctx["entities"]:
        identity = {**entity, "description": "", "aliases": [], "attributes": []}
        if add("entities", identity):
            names[entity["id"]] = entity["name"]

    for rel in writer_ctx["relationships"]:
        if rel["source_id"] in names and rel["target_id"] in names:
            if not add("relationships", rel):
                add("relationships", {**rel, "description": ""})

    rule_count = 0
    for system in writer_ctx["systems"]:
        core = {**system, "data": {}, "constraints": []}
        if not add("systems", core):
            continue
        for raw in system["constraints"]:
            rule = raw.strip()
            if not rule:
                continue
            if rule_count:
                cost = len(f"\n{rule_count + 1}. {rule}")
            else:
                cost = len(extract_narrative_constraints({"systems": [{"constraints": [rule]}]}))
            if cost <= remaining:
                core["constraints"].append(rule)
                remaining -= cost
                rule_count += 1

    by_id = {entity["id"]: entity for entity in writer_ctx["entities"]}
    for entity in result["entities"]:
        full = by_id[entity["id"]]
        for field in ("description", "attributes", "aliases"):
            cost = size({"entities": [{**entity, field: full[field]}]}) - size({"entities": [entity]})
            if cost <= remaining:
                entity[field] = full[field]
                remaining -= cost

    systems = {system["id"]: system for system in writer_ctx["systems"]}
    for core in result["systems"]:
        data = systems[core["id"]]["data"]
        cost = size({"systems": [{**core, "data": data}]}) - size({"systems": [core]})
        if cost <= remaining:
            core["data"] = data
            remaining -= cost

    result["debug"] = {**writer_ctx.get("debug", {}), "relevant_entity_ids": sorted(names)}
    return result


def assemble_writer_context(db: Session, novel_id: int, chapter_text: str) -> dict[str, Any]:
    language = db.query(Novel.language).filter_by(id=novel_id).scalar()
    policy = get_language_policy(language, sample_text=chapter_text)
    text = policy.normalize_for_matching(chapter_text)
    confirmed = db.query(WorldEntity).filter_by(novel_id=novel_id, status="confirmed")
    identities = confirmed.options(load_only(WorldEntity.name, WorldEntity.aliases)).all()
    matches, ambiguous = _find_relevant_entities(identities, policy, text)
    by_id = {entity.id: entity for entity in identities}

    tokenizer = get_tokenizer(policy.language)
    common_words = load_common_words(policy.language)

    def terms(value):
        words = {policy.normalize_token(word) for word in tokenizer.tokenize(policy.normalize_for_matching(value))}
        return {word for word in words - common_words if len(word) > 1 and word.isalpha()}

    scene_terms = terms(text)

    def includes(value):
        return bool(scene_terms & terms(value))

    selected = set(matches)
    relationships = []
    indirect = defaultdict(list)
    if matches:
        nearby = db.query(WorldRelationship).filter(
            WorldRelationship.novel_id == novel_id, WorldRelationship.status == "confirmed",
            WorldRelationship.visibility != VIS_HIDDEN,
            WorldRelationship.source_id.in_(matches) | WorldRelationship.target_id.in_(matches),
        ).order_by(WorldRelationship.id)
        for rel in nearby:
            src, dst = rel.source_id, rel.target_id
            if src not in by_id or dst not in by_id:
                continue
            if src in matches and dst in matches:
                relationships.append(rel)
                continue
            anchor, other = (src, dst) if src in matches else (dst, src)
            description = policy.normalize_for_matching(rel.description)
            for keyword in _iter_entity_keywords(by_id[anchor]):
                description = description.replace(policy.normalize_for_matching(keyword), " ")
            for cue in scene_terms & (terms(rel.label) | terms(description)):
                indirect[anchor, cue].append((other, rel))

    chosen = {rel.id: rel for rel in relationships}
    for candidates in indirect.values():
        if len({other for other, _ in candidates}) == 1:
            for other, rel in candidates:
                selected.add(other)
                chosen[rel.id] = rel
    relationships_out = [
        {"id": rel.id, "source_id": rel.source_id, "target_id": rel.target_id, "label": rel.label,
         "description": rel.description or "", "visibility": rel.visibility}
        for rel in chosen.values()
    ]

    entities_out = []
    if selected:
        entities = confirmed.filter(WorldEntity.id.in_(selected)).options(joinedload(WorldEntity.attributes)).all()
        for entity in entities:
            match = matches.get(entity.id)
            # An indirect mention needs an identity for the relationship, not the other character's biography.
            attrs = sorted(entity.attributes, key=lambda attr: (attr.sort_order, attr.key)) if match else []
            entities_out.append({
                "id": entity.id, "name": entity.name, "entity_type": entity.entity_type,
                "aliases": list(entity.aliases or []) if match else [],
                "description": (entity.description or "") if match else "",
                "attributes": [
                    {"id": attr.id, "key": attr.key, "surface": attr.surface,
                     "visibility": attr.visibility, "sort_order": attr.sort_order}
                    for attr in attrs if attr.visibility == VIS_ACTIVE
                    or (attr.visibility != VIS_HIDDEN and (includes(attr.key) or includes(attr.surface)))
                ],
                "match_count": match.count if match else 0, "matched_terms": sorted(match.terms) if match else [],
            })
    entities_out.sort(key=lambda ent: (-ent["match_count"], ent["name"]))

    systems_out = []
    systems = db.query(WorldSystem).filter(
        WorldSystem.novel_id == novel_id, WorldSystem.status == "confirmed", WorldSystem.visibility != VIS_HIDDEN,
    ).order_by(WorldSystem.visibility, WorldSystem.name)
    for system in systems:
        whole = system.visibility == VIS_ACTIVE or includes(system.name)
        data = _scene_system_data(system, includes, matches, whole=whole)
        rules = [rule for rule in system.constraints or [] if whole or includes(rule)]
        if whole or rules or any(data.values()) or includes(system.description):
            systems_out.append({
                "id": system.id, "name": system.name, "display_type": system.display_type,
                "description": system.description or "", "data": data, "constraints": rules,
                "visibility": system.visibility, "status": system.status,
            })

    return {"entities": entities_out, "relationships": relationships_out, "systems": systems_out,
            "debug": {"relevant_entity_ids": sorted(selected), "ambiguous_keywords_disabled": sorted(ambiguous)}}
