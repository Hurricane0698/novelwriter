# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Deterministic research-tool surface for copilot tool-loop runs."""

from __future__ import annotations

import json
import heapq
import logging
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.copilot.tool_contract import (
    ResearchToolCatalog,
    ResearchToolSpec,
    ToolRuntimeMetadata,
)
from app.core.indexing import WINDOW_INDEX_STATUS_FRESH
from app.core.copilot.messages import CopilotTextKey, get_copilot_text
from app.core.copilot.scope import ScopeSnapshot
from app.core.copilot.scope_shared import NovelScopeValue
from app.core.copilot.sync_runtime import check_sync_cancelled
from app.core.copilot.workspace import EvidencePack, Workspace, make_pack_id
from app.language_policy import get_language_policy
from app.models import Chapter, Novel, WorldEntity, WorldRelationship, WorldSystem

logger = logging.getLogger(__name__)

MAX_EVIDENCE_PACKS = 12
MAX_OPEN_MANY_PACKS = 3
DEFAULT_OPEN_MANY_EXPAND_CHARS = 1200
MAX_OPEN_MANY_EXPAND_CHARS = 2000
_QUERY_TERM_SPLIT_RE = re.compile(r"[\s,，、；;|/]+")


def _tool_text(
    interaction_locale: str,
    text_key: CopilotTextKey,
    **params: object,
) -> str:
    return get_copilot_text(text_key, locale=interaction_locale, **params)


def _append_tool_labeled_line(
    text: str,
    *,
    interaction_locale: str,
    label_key: CopilotTextKey,
    value: str,
) -> str:
    label = _tool_text(interaction_locale, label_key)
    return f"{text}\n{label}: {value}"

RESEARCH_TOOL_CATALOG = ResearchToolCatalog(
    specs=(
        ResearchToolSpec(
            name="load_scope_snapshot",
            description=(
                "Re-load world-model state: entities, relationships, systems, drafts. "
                "Use when you need a fresh view."
            ),
            parameters_schema={"type": "object", "properties": {}, "required": []},
            runtime=ToolRuntimeMetadata(
                execution_path="runtime",
                snapshot_policy="refresh_scope",
                fresh_snapshot_sensitive=True,
            ),
        ),
        ResearchToolSpec(
            name="find",
            description=(
                "Research query. Returns evidence packs with stable IDs for "
                "progressive disclosure."
            ),
            parameters_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Free-text research query",
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["story_text", "world_rows", "drafts", "all"],
                        "description": "Search scope filter (default: all)",
                    },
                },
                "required": ["query"],
            },
            runtime=ToolRuntimeMetadata(
                snapshot_policy="snapshot_bound",
                fresh_snapshot_sensitive=True,
                auto_follow_up_hint="open_first_chapter_pack",
            ),
        ),
        ResearchToolSpec(
            name="open",
            description="Expand a previously-found evidence pack to see full content.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "pack_id": {
                        "type": "string",
                        "description": "Pack ID from a find result",
                    },
                    "expand_chars": {
                        "type": "integer",
                        "description": "Max chars to expand (default 2000)",
                    },
                },
                "required": ["pack_id"],
            },
            runtime=ToolRuntimeMetadata(
                snapshot_policy="workspace_memory",
                fresh_snapshot_sensitive=False,
            ),
        ),
        ResearchToolSpec(
            name="open_many",
            description=(
                "Expand multiple previously-found evidence packs in one call. "
                "Use when you need several independent evidence reads, especially "
                "chapter packs."
            ),
            parameters_schema={
                "type": "object",
                "properties": {
                    "pack_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Pack IDs from find results. Prefer 2-3 packs that are "
                            "independent and worth comparing."
                        ),
                    },
                    "expand_chars": {
                        "type": "integer",
                        "description": (
                            "Max chars to expand per pack (default 1200, capped lower "
                            "than open() to control prompt growth)"
                        ),
                    },
                },
                "required": ["pack_ids"],
            },
            runtime=ToolRuntimeMetadata(
                snapshot_policy="workspace_memory",
                fresh_snapshot_sensitive=False,
            ),
        ),
        ResearchToolSpec(
            name="read",
            description=(
                "Read live world state for specific targets "
                "(entities, relationships, systems)."
            ),
            parameters_schema={
                "type": "object",
                "properties": {
                    "target_refs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": ["entity", "relationship", "system"],
                                },
                                "id": {"type": "integer"},
                            },
                            "required": ["type", "id"],
                        },
                        "description": "Targets to read",
                    },
                },
                "required": ["target_refs"],
            },
            runtime=ToolRuntimeMetadata(
                snapshot_policy="live_read",
                fresh_snapshot_sensitive=True,
            ),
        ),
    )
)


def get_research_tool_spec(tool_name: str) -> ResearchToolSpec | None:
    return RESEARCH_TOOL_CATALOG.get(tool_name)


def dispatch_tool(
    tool_name: str,
    tool_args: dict[str, Any],
    db: Session,
    novel_id: int,
    snapshot: ScopeSnapshot,
    workspace: Workspace,
    interaction_locale: str = "zh",
) -> str:
    """Dispatch a single research tool call."""
    tool_spec = get_research_tool_spec(tool_name)
    if tool_spec is None or tool_spec.runtime.execution_path != "dispatch":
        return json.dumps(
            {
                "error": _tool_text(
                    interaction_locale,
                    CopilotTextKey.TOOL_UNKNOWN_TOOL,
                    tool_name=tool_name,
                ),
            },
            ensure_ascii=False,
        )
    if tool_name == "find":
        return _tool_find(
            tool_args.get("query", ""),
            tool_args.get("scope", "all"),
            db,
            novel_id,
            snapshot.novel,
            snapshot,
            workspace,
            interaction_locale,
        )
    if tool_name == "open":
        return _tool_open(
            tool_args.get("pack_id", ""),
            tool_args.get("expand_chars", 2000),
            db,
            snapshot.novel,
            workspace,
            interaction_locale,
        )
    if tool_name == "open_many":
        return _tool_open_many(
            tool_args.get("pack_ids", []),
            tool_args.get("expand_chars", DEFAULT_OPEN_MANY_EXPAND_CHARS),
            db,
            snapshot.novel,
            workspace,
            interaction_locale,
        )
    if tool_name == "read":
        return _tool_read(tool_args.get("target_refs", []), db, novel_id, snapshot)
    return json.dumps(
        {
            "error": _tool_text(
                interaction_locale,
                CopilotTextKey.TOOL_UNKNOWN_TOOL,
                tool_name=tool_name,
            ),
        },
        ensure_ascii=False,
    )


def tool_load_scope_snapshot(snapshot: ScopeSnapshot) -> str:
    """Render a structured summary for the live scope snapshot tool."""
    entity_names = [
        f"{entity.name}({entity.entity_type})" + (" [draft]" if entity.status == "draft" else "")
        for entity in snapshot.entities[:40]
    ]
    draft_count = (
        len(snapshot.draft_entities)
        + len(snapshot.draft_relationships)
        + len(snapshot.draft_systems)
    )
    return json.dumps({
        "profile": snapshot.profile,
        "focus_variant": snapshot.focus_variant,
        "focus_entity_id": snapshot.focus_entity_id,
        "entities": entity_names,
        "entity_count": len(snapshot.entities),
        "relationship_count": len(snapshot.relationships),
        "systems": [system.name for system in snapshot.systems],
        "draft_count": draft_count,
    }, ensure_ascii=False)


@dataclass(frozen=True, slots=True)
class QueryTerm:
    raw: str
    normalized: str


def _extract_query_terms(query: str, language: str | None) -> list[QueryTerm]:
    raw_query = (query or "").strip()
    if not raw_query:
        return []

    policy = get_language_policy(language, sample_text=raw_query)
    raw_chunks = [chunk.strip() for chunk in _QUERY_TERM_SPLIT_RE.split(raw_query) if chunk.strip()]
    candidate_terms: list[str] = []

    if len(raw_chunks) > 1:
        candidate_terms.extend(raw_chunks)
    else:
        candidate_terms.append(raw_query)
        try:
            from app.core.indexing.builder import get_tokenizer

            tokenizer = get_tokenizer(policy.language)
            candidate_terms.extend(tokenizer.tokenize(raw_query))
        except Exception:
            logger.debug("Copilot query tokenization fallback engaged", exc_info=True)

    extracted: list[QueryTerm] = []
    seen: set[str] = set()
    for raw_term in candidate_terms:
        cleaned = policy.normalize_token(raw_term)
        normalized = policy.normalize_for_matching(cleaned)
        if len(normalized) < 2 or normalized in seen:
            continue
        seen.add(normalized)
        extracted.append(QueryTerm(raw=cleaned, normalized=normalized))

    return extracted[:12]


def _find_term_matches(
    text: str,
    query_terms: list[QueryTerm],
    *,
    language: str | None,
) -> list[tuple[int, int, QueryTerm]]:
    if not text or not query_terms:
        return []

    policy = get_language_policy(language, sample_text=text)
    normalized_text = policy.normalize_for_matching(text)
    matches: list[tuple[int, int, QueryTerm]] = []

    for term in query_terms:
        search_from = 0
        while search_from < len(normalized_text):
            pos = normalized_text.find(term.normalized, search_from)
            if pos == -1:
                break
            end = pos + len(term.normalized)
            if policy.match_has_word_boundaries(normalized_text, pos, end):
                matches.append((pos, end, term))
            search_from = max(pos + 1, end)

    matches.sort(key=lambda item: item[0])
    return matches


def _resolve_excerpt_window(
    text: str,
    matches: list[tuple[int, int, QueryTerm]],
) -> tuple[int, int]:
    if not text:
        return 0, 0
    if not matches:
        return 0, min(len(text), 500)

    cluster_start = matches[0][0]
    cluster_end = matches[0][1]
    for start, end, _ in matches[1:4]:
        if start - cluster_end > 220:
            break
        cluster_end = end

    start = max(0, cluster_start - 200)
    end = min(len(text), cluster_end + 320)
    if end <= start:
        end = min(len(text), start + 500)
    return start, end


def _summarize_matched_terms(matches: list[tuple[int, int, QueryTerm]]) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for _, _, term in matches:
        if term.normalized in seen:
            continue
        seen.add(term.normalized)
        terms.append(term.raw)
    return terms


def _tool_find(
    query: str,
    scope_filter: str,
    db: Session,
    _novel_id: int,
    novel: Novel | NovelScopeValue,
    snapshot: ScopeSnapshot,
    workspace: Workspace,
    interaction_locale: str = "zh",
) -> str:
    packs: list[EvidencePack] = []

    if scope_filter in ("world_rows", "all"):
        packs += _find_from_world_rows(query, snapshot, interaction_locale)

    if scope_filter in ("story_text", "all"):
        packs += _find_from_window_index(query, db, _novel_id, novel, snapshot)

    if scope_filter == "drafts":
        packs += _find_from_draft_auditors(snapshot, interaction_locale)

    if len(packs) < 3 and scope_filter in ("story_text", "all"):
        packs += _find_from_chapters(query, db, novel)

    check_sync_cancelled()
    deduped = _deduplicate_packs(packs)[:MAX_EVIDENCE_PACKS]
    for pack in deduped:
        workspace.evidence_packs[pack.pack_id] = pack

    return json.dumps({
        "packs": [
            {
                "pack_id": pack.pack_id,
                "preview": pack.preview_excerpt[:300],
                "anchor_terms": pack.anchor_terms,
                "support_count": pack.support_count,
            }
            for pack in deduped
        ],
        "total_found": len(deduped),
    }, ensure_ascii=False)


def _find_from_world_rows(
    query: str,
    snapshot: ScopeSnapshot,
    interaction_locale: str = "zh",
) -> list[EvidencePack]:
    packs: list[EvidencePack] = []
    query_terms = _extract_query_terms(query, snapshot.novel_language)
    if not query_terms:
        return []

    for entity in snapshot.entities:
        attrs = snapshot.attributes_by_entity.get(entity.id, [])
        attr_text = "; ".join(f"{attr.key}={attr.surface[:80]}" for attr in attrs[:5])
        match_terms = _summarize_matched_terms(
            _find_term_matches(
                "\n".join([entity.name, *(entity.aliases or []), entity.description or "", attr_text]),
                query_terms,
                language=snapshot.novel_language,
            )
        )
        if not match_terms:
            continue

        excerpt = f"{entity.name} ({entity.entity_type}): {(entity.description or '')[:300]}"
        if attr_text:
            excerpt = _append_tool_labeled_line(
                excerpt,
                interaction_locale=interaction_locale,
                label_key=CopilotTextKey.TEXT_ATTRIBUTES_LABEL,
                value=attr_text,
            )

        packs.append(EvidencePack(
            pack_id=make_pack_id(f"pk_ent_{entity.id}", excerpt[:100]),
            source_refs=[{"type": "entity", "id": entity.id}],
            preview_excerpt=excerpt[:500],
            anchor_terms=match_terms[:5],
            support_count=len(match_terms),
            related_targets=[{"type": "entity", "id": entity.id, "name": entity.name}],
        ))

    for relationship in snapshot.relationships:
        src = snapshot.entities_by_id.get(relationship.source_id)
        tgt = snapshot.entities_by_id.get(relationship.target_id)
        src_name = src.name if src else f"#{relationship.source_id}"
        tgt_name = tgt.name if tgt else f"#{relationship.target_id}"
        text = f"{src_name} --[{relationship.label}]--> {tgt_name}: {(relationship.description or '')[:200]}"
        match_terms = _summarize_matched_terms(
            _find_term_matches(text, query_terms, language=snapshot.novel_language)
        )
        if not match_terms:
            continue
        packs.append(EvidencePack(
            pack_id=make_pack_id(f"pk_rel_{relationship.id}", text[:100]),
            source_refs=[{"type": "relationship", "id": relationship.id}],
            preview_excerpt=text[:500],
            anchor_terms=match_terms[:5],
            support_count=len(match_terms),
            related_targets=[
                {"type": "entity", "id": relationship.source_id, "name": src_name},
                {"type": "entity", "id": relationship.target_id, "name": tgt_name},
            ],
        ))

    for system in snapshot.systems:
        text = f"{system.name} ({system.display_type}): {(system.description or '')[:300]}"
        if system.constraints:
            text = _append_tool_labeled_line(
                text,
                interaction_locale=interaction_locale,
                label_key=CopilotTextKey.TEXT_CONSTRAINTS_LABEL,
                value="; ".join(str(item)[:80] for item in system.constraints[:6]),
            )
        match_terms = _summarize_matched_terms(
            _find_term_matches(text, query_terms, language=snapshot.novel_language)
        )
        if not match_terms:
            continue
        packs.append(EvidencePack(
            pack_id=make_pack_id(f"pk_sys_{system.id}", text[:100]),
            source_refs=[{"type": "system", "id": system.id}],
            preview_excerpt=text[:500],
            anchor_terms=match_terms[:5],
            support_count=len(match_terms),
            related_targets=[{"type": "system", "id": system.id, "name": system.name}],
        ))

    return packs


def _find_from_window_index(
    query: str,
    db: Session,
    _novel_id: int,
    novel: Novel | NovelScopeValue,
    snapshot: ScopeSnapshot,
) -> list[EvidencePack]:
    from app.core.indexing.window_index import NovelIndex

    lifecycle = snapshot.window_index_state
    if not (
        lifecycle
        and lifecycle.status == WINDOW_INDEX_STATUS_FRESH
        and lifecycle.has_payload
        and novel.window_index
    ):
        return []

    query_terms = _extract_query_terms(query, novel.language or snapshot.novel_language)
    if not query_terms:
        return []

    candidate_name_rows: list[tuple[str, list[str]]] = []
    for entity in snapshot.entities:
        match_terms = _summarize_matched_terms(
            _find_term_matches(
                "\n".join([entity.name, *(entity.aliases or [])]),
                query_terms,
                language=novel.language or snapshot.novel_language,
            )
        )
        if match_terms:
            candidate_name_rows.append((entity.name, match_terms))

    candidate_name_rows.sort(key=lambda item: (-len(item[1]), item[0]))
    if not candidate_name_rows:
        candidate_name_rows = [(query.strip(), [query.strip()])]

    packs: list[EvidencePack] = []
    try:
        index = NovelIndex.from_msgpack(novel.window_index)
    except Exception:
        logger.debug("Window index load failed in find", exc_info=True)
        return []

    seen_windows: set[tuple[int, int]] = set()
    for name, anchor_terms in candidate_name_rows[:5]:
        windows = index.find_entity_passages(name, limit=4)
        for window in windows:
            key = (window.chapter_id, window.start_pos)
            if key in seen_windows:
                continue
            seen_windows.add(key)

            chapter = db.get(Chapter, window.chapter_id)
            if not chapter or not chapter.content:
                continue
            start = max(0, window.start_pos)
            end = min(len(chapter.content), window.end_pos)
            text = chapter.content[start:end]
            if not text.strip():
                continue

            packs.append(EvidencePack(
                pack_id=make_pack_id(f"pk_ch_{chapter.id}_{start}_{end}", text[:100]),
                source_refs=[{
                    "type": "chapter",
                    "chapter_id": chapter.id,
                    "chapter_number": chapter.chapter_number,
                    "start_pos": start,
                    "end_pos": end,
                }],
                preview_excerpt=text[:500],
                anchor_terms=anchor_terms[:5] or [name],
                support_count=max(window.entity_count, len(anchor_terms)),
                related_targets=[{"type": "chapter", "chapter_id": chapter.id}],
            ))

    return packs


def _find_from_draft_auditors(
    snapshot: ScopeSnapshot,
    interaction_locale: str = "zh",
) -> list[EvidencePack]:
    packs: list[EvidencePack] = []

    for entity in snapshot.draft_entities:
        issues: list[str] = []
        if not entity.description or not entity.description.strip():
            issues.append(_tool_text(interaction_locale, CopilotTextKey.TOOL_ISSUE_MISSING_DESCRIPTION))
        if not entity.aliases:
            issues.append(_tool_text(interaction_locale, CopilotTextKey.TOOL_ISSUE_NO_ALIASES))
        attrs = snapshot.attributes_by_entity.get(entity.id, [])
        if not attrs:
            issues.append(_tool_text(interaction_locale, CopilotTextKey.TOOL_ISSUE_NO_ATTRIBUTES))
        if issues:
            excerpt = _tool_text(
                interaction_locale,
                CopilotTextKey.TOOL_DRAFT_ENTITY_ISSUES_EXCERPT,
                entity_name=entity.name,
                entity_type=entity.entity_type,
                issues=", ".join(issues),
            )
            packs.append(EvidencePack(
                pack_id=make_pack_id(f"pk_draft_ent_{entity.id}", excerpt),
                source_refs=[{"type": "entity", "id": entity.id}],
                preview_excerpt=excerpt,
                anchor_terms=[entity.name],
                support_count=len(issues),
                related_targets=[{"type": "entity", "id": entity.id, "name": entity.name}],
                conflict_group="draft_quality",
            ))

    for relationship in snapshot.draft_relationships:
        if not relationship.description or not relationship.description.strip():
            src = snapshot.entities_by_id.get(relationship.source_id)
            tgt = snapshot.entities_by_id.get(relationship.target_id)
            excerpt = _tool_text(
                interaction_locale,
                CopilotTextKey.TOOL_DRAFT_RELATIONSHIP_MISSING_DESCRIPTION_EXCERPT,
                source_name=src.name if src else "?",
                label=relationship.label,
                target_name=tgt.name if tgt else "?",
            )
            packs.append(EvidencePack(
                pack_id=make_pack_id(f"pk_draft_rel_{relationship.id}", excerpt),
                source_refs=[{"type": "relationship", "id": relationship.id}],
                preview_excerpt=excerpt,
                anchor_terms=[relationship.label],
                support_count=1,
                related_targets=[],
                conflict_group="draft_quality",
            ))

    for system in snapshot.draft_systems:
        issues: list[str] = []
        if not system.description or not system.description.strip():
            issues.append(_tool_text(interaction_locale, CopilotTextKey.TOOL_ISSUE_MISSING_DESCRIPTION))
        if not system.constraints:
            issues.append(_tool_text(interaction_locale, CopilotTextKey.TOOL_ISSUE_NO_CONSTRAINTS))
        if issues:
            excerpt = _tool_text(
                interaction_locale,
                CopilotTextKey.TOOL_DRAFT_SYSTEM_ISSUES_EXCERPT,
                system_name=system.name,
                issues=", ".join(issues),
            )
            packs.append(EvidencePack(
                pack_id=make_pack_id(f"pk_draft_sys_{system.id}", excerpt),
                source_refs=[{"type": "system", "id": system.id}],
                preview_excerpt=excerpt,
                anchor_terms=[system.name],
                support_count=len(issues),
                related_targets=[{"type": "system", "id": system.id, "name": system.name}],
                conflict_group="draft_quality",
            ))

    return packs


def _find_from_chapters(query: str, db: Session, novel: Novel | NovelScopeValue) -> list[EvidencePack]:
    query_terms = _extract_query_terms(query, novel.language)
    if not query_terms:
        return []

    scored: list[tuple[int, int, int, EvidencePack]] = []
    chapters = (
        db.query(Chapter.id, Chapter.chapter_number, Chapter.content)
        .filter(Chapter.novel_id == novel.id)
        .order_by(Chapter.chapter_number.asc())
        .yield_per(1)
    )
    for chapter in chapters:
        check_sync_cancelled()
        if not chapter.content:
            continue
        count, matched_terms, first_matches = _scan_chapter_matches(
            chapter.content, query_terms, language=novel.language
        )
        if not count:
            continue
        # The smallest heap item is the worst retained chapter. Chapter numbers
        # are unique per novel, so ties never compare EvidencePack instances.
        rank = (len(matched_terms), count, -chapter.chapter_number)
        if len(scored) == MAX_EVIDENCE_PACKS and rank <= scored[0][:3]:
            continue
        start, end = _resolve_excerpt_window(chapter.content, first_matches)
        text = chapter.content[start:end]
        pack = EvidencePack(
            pack_id=make_pack_id(f"pk_ch_{chapter.id}_{start}_{end}", text[:100]),
            source_refs=[{
                "type": "chapter",
                "chapter_id": chapter.id,
                "chapter_number": chapter.chapter_number,
                "start_pos": start,
                "end_pos": end,
            }],
            preview_excerpt=text[:500],
            anchor_terms=matched_terms[:5],
            support_count=len(matched_terms),
            related_targets=[{"type": "chapter", "chapter_id": chapter.id}],
        )
        item = (*rank, pack)
        if len(scored) < MAX_EVIDENCE_PACKS:
            heapq.heappush(scored, item)
        else:
            heapq.heapreplace(scored, item)

    scored.sort(key=lambda item: item[:3], reverse=True)
    return [item[3] for item in scored]


def _scan_chapter_matches(
    text: str,
    query_terms: list[QueryTerm],
    *,
    language: str | None,
) -> tuple[int, list[str], list[tuple[int, int, QueryTerm]]]:
    """Retain counts, term order and the four positions used by the excerpt.

    Scanning still covers every chapter and every non-overlapping occurrence.
    At most four positions per query term are kept, independent of frequency.
    Stable sorting preserves the old query-term order when positions tie.
    """
    policy = get_language_policy(language, sample_text=text)
    normalized_text = policy.normalize_for_matching(text)
    count = 0
    first_matches: list[tuple[int, int, QueryTerm]] = []
    first_per_term: list[tuple[int, int, QueryTerm]] = []
    for term in query_terms:
        check_sync_cancelled()
        search_from = 0
        term_count = 0
        while search_from < len(normalized_text):
            pos = normalized_text.find(term.normalized, search_from)
            if pos == -1:
                break
            end = pos + len(term.normalized)
            if policy.match_has_word_boundaries(normalized_text, pos, end):
                if term_count < 4:
                    first_matches.append((pos, end, term))
                if not term_count:
                    first_per_term.append((pos, end, term))
                term_count += 1
                count += 1
            search_from = max(pos + 1, end)
            if not count % 1024:
                check_sync_cancelled()
    first_matches.sort(key=lambda item: item[0])
    first_per_term.sort(key=lambda item: item[0])
    return count, _summarize_matched_terms(first_per_term), first_matches[:4]


def _deduplicate_packs(packs: list[EvidencePack]) -> list[EvidencePack]:
    seen: dict[str, EvidencePack] = {}
    for pack in packs:
        if pack.pack_id not in seen or pack.support_count > seen[pack.pack_id].support_count:
            seen[pack.pack_id] = pack
    return sorted(
        seen.values(),
        key=lambda pack: (-(pack.support_count or 0), pack.pack_id),
    )


def _tool_open(
    pack_id: str,
    expand_chars: int,
    db: Session,
    _novel: Novel | NovelScopeValue,
    workspace: Workspace,
    interaction_locale: str = "zh",
) -> str:
    result, found = _expand_pack_result(
        pack_id=pack_id,
        expand_chars=expand_chars,
        workspace=workspace,
        interaction_locale=interaction_locale,
        chapters_by_id=None,
        db=db,
    )
    if not found:
        return json.dumps({"error": result["error"]}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False)


def _tool_open_many(
    pack_ids: list[Any],
    expand_chars: int,
    db: Session,
    _novel: Novel | NovelScopeValue,
    workspace: Workspace,
    interaction_locale: str = "zh",
) -> str:
    normalized_pack_ids, overflow_pack_ids = _normalize_pack_ids(pack_ids)
    requested_count = len(normalized_pack_ids) + len(overflow_pack_ids)
    if overflow_pack_ids:
        return json.dumps(
            {
                "error": _tool_text(
                    interaction_locale,
                    CopilotTextKey.TOOL_OPEN_MANY_TOO_MANY_PACKS,
                    max_count=MAX_OPEN_MANY_PACKS,
                ),
                "results": [],
                "opened_count": 0,
                "requested_count": requested_count,
                "max_pack_ids": MAX_OPEN_MANY_PACKS,
            },
            ensure_ascii=False,
        )
    if not normalized_pack_ids:
        return json.dumps(
            {
                "error": _tool_text(
                    interaction_locale,
                    CopilotTextKey.TOOL_OPEN_MANY_NO_PACKS,
                ),
                "results": [],
                "opened_count": 0,
                "requested_count": 0,
            },
            ensure_ascii=False,
        )

    expand_chars = min(
        expand_chars or DEFAULT_OPEN_MANY_EXPAND_CHARS,
        MAX_OPEN_MANY_EXPAND_CHARS,
    )

    chapter_ids = _collect_chapter_ids_for_packs(normalized_pack_ids, workspace)
    chapters_by_id: dict[int, Chapter] | None = None
    if chapter_ids:
        chapters_by_id = {
            chapter.id: chapter
            for chapter in (
                db.query(Chapter).filter(Chapter.id.in_(chapter_ids)).all()
            )
        }

    results: list[dict[str, Any]] = []
    opened_count = 0
    for pack_id in normalized_pack_ids:
        result, found = _expand_pack_result(
            pack_id=pack_id,
            expand_chars=expand_chars,
            workspace=workspace,
            interaction_locale=interaction_locale,
            chapters_by_id=chapters_by_id,
            db=db,
        )
        if found:
            opened_count += 1
        results.append(result)

    failed_results = [
        result
        for result in results
        if isinstance(result.get("error"), str) and result["error"].strip()
    ]
    response: dict[str, Any] = {
        "results": results,
        "opened_count": opened_count,
        "requested_count": len(normalized_pack_ids),
    }
    if failed_results:
        response["error"] = _tool_text(
            interaction_locale,
            CopilotTextKey.TOOL_OPEN_MANY_FAILED_COUNT,
            failed_count=len(failed_results),
            requested_count=len(normalized_pack_ids),
        )
        response["failed_count"] = len(failed_results)
        response["failed_pack_ids"] = [
            str(result.get("pack_id") or "")
            for result in failed_results
            if str(result.get("pack_id") or "")
        ]

    return json.dumps(
        response,
        ensure_ascii=False,
    )


def _normalize_pack_ids(pack_ids: list[Any] | Any) -> tuple[list[str], list[str]]:
    if not isinstance(pack_ids, list):
        pack_ids = [pack_ids]

    normalized: list[str] = []
    overflow: list[str] = []
    seen: set[str] = set()
    for raw in pack_ids:
        pack_id = str(raw or "").strip()
        if not pack_id or pack_id in seen:
            continue
        seen.add(pack_id)
        if len(normalized) >= MAX_OPEN_MANY_PACKS:
            overflow.append(pack_id)
            continue
        normalized.append(pack_id)
    return normalized, overflow


def _collect_chapter_ids_for_packs(
    pack_ids: list[str],
    workspace: Workspace,
) -> list[int]:
    chapter_ids: list[int] = []
    seen: set[int] = set()
    for pack_id in pack_ids:
        pack = workspace.evidence_packs.get(pack_id)
        if not pack:
            continue
        for ref in pack.source_refs:
            chapter_id = ref.get("chapter_id")
            if ref.get("type") != "chapter" or not isinstance(chapter_id, int):
                continue
            if chapter_id in seen:
                continue
            seen.add(chapter_id)
            chapter_ids.append(chapter_id)
    return chapter_ids


def _expand_pack_result(
    *,
    pack_id: str,
    expand_chars: int,
    workspace: Workspace,
    interaction_locale: str,
    chapters_by_id: dict[int, Chapter] | None,
    db: Session,
) -> tuple[dict[str, Any], bool]:
    pack = workspace.evidence_packs.get(pack_id)
    if not pack:
        return (
            {
                "pack_id": pack_id,
                "error": _tool_text(
                    interaction_locale,
                    CopilotTextKey.TOOL_UNKNOWN_PACK,
                    pack_id=pack_id,
                ),
            },
            False,
        )

    normalized_expand_chars = min(expand_chars or 2000, 4000)
    expanded_text = _expand_pack_text(
        pack,
        expand_chars=normalized_expand_chars,
        chapters_by_id=chapters_by_id,
        db=db,
    )
    if expanded_text and (
        pack.expanded_text is None or len(expanded_text) > len(pack.expanded_text)
    ):
        check_sync_cancelled()
        pack.expanded_text = expanded_text

    if pack_id not in workspace.opened_pack_ids:
        check_sync_cancelled()
        workspace.opened_pack_ids.append(pack_id)

    return (
        {
            "pack_id": pack_id,
            "expanded_text": pack.expanded_text or pack.preview_excerpt,
            "source_refs": pack.source_refs,
        },
        True,
    )


def _expand_pack_text(
    pack: EvidencePack,
    *,
    expand_chars: int,
    chapters_by_id: dict[int, Chapter] | None,
    db: Session,
) -> str | None:
    for ref in pack.source_refs:
        if ref.get("type") != "chapter" or not ref.get("chapter_id"):
            continue
        chapter_id = ref["chapter_id"]
        chapter = (
            chapters_by_id.get(chapter_id)
            if chapters_by_id is not None
            else db.get(Chapter, chapter_id)
        )
        if chapter and chapter.content:
            start = max(0, ref.get("start_pos", 0) - 200)
            end = min(len(chapter.content), ref.get("end_pos", 0) + expand_chars)
            return chapter.content[start:end]
    return None


def _tool_read(
    target_refs: list[dict[str, Any]],
    db: Session,
    novel_id: int,
    snapshot: ScopeSnapshot,
) -> str:
    results: list[dict[str, Any]] = []
    for ref in target_refs[:10]:
        ref_type = ref.get("type", "")
        ref_id = ref.get("id")
        if not ref_id:
            continue
        if ref_type == "entity":
            entity = snapshot.entities_by_id.get(ref_id)
            if not entity:
                entity = (
                    db.query(WorldEntity)
                    .filter(WorldEntity.id == ref_id, WorldEntity.novel_id == novel_id)
                    .first()
                )
            if entity:
                attrs = snapshot.attributes_by_entity.get(entity.id, [])
                results.append({
                    "type": "entity",
                    "id": entity.id,
                    "name": entity.name,
                    "entity_type": entity.entity_type,
                    "description": (entity.description or "")[:500],
                    "aliases": entity.aliases or [],
                    "status": entity.status,
                    "attributes": [
                        {
                            "key": attr.key,
                            "surface": attr.surface[:200],
                            "visibility": attr.visibility,
                        }
                        for attr in attrs[:10]
                    ],
                })
        elif ref_type == "relationship":
            relationship = next(
                (rel for rel in snapshot.relationships if rel.id == ref_id),
                None,
            )
            if not relationship:
                relationship = (
                    db.query(WorldRelationship)
                    .filter(WorldRelationship.id == ref_id, WorldRelationship.novel_id == novel_id)
                    .first()
                )
            if relationship:
                src = snapshot.entities_by_id.get(relationship.source_id)
                tgt = snapshot.entities_by_id.get(relationship.target_id)
                results.append({
                    "type": "relationship",
                    "id": relationship.id,
                    "label": relationship.label,
                    "source": {"id": relationship.source_id, "name": src.name if src else "?"},
                    "target": {"id": relationship.target_id, "name": tgt.name if tgt else "?"},
                    "description": (relationship.description or "")[:300],
                    "status": relationship.status,
                })
        elif ref_type == "system":
            system = next((item for item in snapshot.systems if item.id == ref_id), None)
            if not system:
                system = (
                    db.query(WorldSystem)
                    .filter(WorldSystem.id == ref_id, WorldSystem.novel_id == novel_id)
                    .first()
                )
            if system:
                results.append({
                    "type": "system",
                    "id": system.id,
                    "name": system.name,
                    "display_type": system.display_type,
                    "description": (system.description or "")[:300],
                    "status": system.status,
                })

    return json.dumps({"results": results}, ensure_ascii=False)
