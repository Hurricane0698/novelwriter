# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Backend-sourced evidence gathering for copilot."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core.copilot.messages import CopilotTextKey
from app.core.indexing import (
    WINDOW_INDEX_STATUS_FAILED,
    WINDOW_INDEX_STATUS_FRESH,
    WINDOW_INDEX_STATUS_MISSING,
    WINDOW_INDEX_STATUS_STALE,
)
from app.models import Chapter, Novel

from .scope_shared import (
    MAX_CHAPTER_EXCERPT_CHARS,
    MAX_EVIDENCE_ITEMS,
    EvidenceItem,
    ScopeSnapshot,
    append_scope_labeled_line,
    scope_text,
)

logger = logging.getLogger(__name__)


def gather_evidence(
    db: Session,
    novel: Novel,
    snapshot: ScopeSnapshot,
    context: dict | None,
    interaction_locale: str = "zh",
) -> list[EvidenceItem]:
    """Gather evidence from backend-known sources BEFORE the LLM call."""
    items: list[EvidenceItem] = []

    if snapshot.profile == "draft_governance":
        _gather_draft_row_evidence(snapshot, items, interaction_locale)
        if snapshot.focus_entity_id is not None:
            _gather_chapter_evidence(
                db, novel, context, snapshot, items, interaction_locale
            )
    else:
        _gather_chapter_evidence(
            db, novel, context, snapshot, items, interaction_locale
        )
        _gather_entity_evidence(snapshot, context, items, interaction_locale)
        _gather_relationship_evidence(snapshot, context, items, interaction_locale)

    return items[:MAX_EVIDENCE_ITEMS]


def _gather_chapter_evidence(
    db: Session,
    novel: Novel,
    context: dict | None,
    snapshot: ScopeSnapshot,
    items: list[EvidenceItem],
    interaction_locale: str,
) -> None:
    """Gather chapter excerpts from window index or tail chapters."""
    from app.core.indexing.window_index import NovelIndex

    lifecycle = snapshot.window_index_state
    use_window_index = bool(
        lifecycle
        and lifecycle.status == WINDOW_INDEX_STATUS_FRESH
        and lifecycle.has_payload
        and novel.window_index
    )

    if context and context.get("entity_id") and use_window_index:
        entity = snapshot.entities_by_id.get(context["entity_id"])
        if entity:
            try:
                index = NovelIndex.from_msgpack(novel.window_index)
                windows = index.find_entity_passages(entity.name, limit=6)
                for window in windows:
                    chapter = db.get(Chapter, window.chapter_id)
                    if chapter and chapter.content:
                        start = max(0, window.start_pos)
                        end = min(len(chapter.content), window.end_pos)
                        text = chapter.content[start:end]
                        if text.strip():
                            items.append(
                                EvidenceItem(
                                    evidence_id=f"ch_{chapter.id}_{start}",
                                    source_type="chapter_excerpt",
                                    source_ref={
                                        "chapter_id": chapter.id,
                                        "chapter_number": chapter.chapter_number,
                                        "start_pos": start,
                                        "end_pos": end,
                                    },
                                    title=scope_text(
                                        interaction_locale,
                                        CopilotTextKey.SCOPE_CHAPTER_WINDOW_TITLE,
                                        chapter_number=chapter.chapter_number,
                                        start=start,
                                        end=end,
                                    ),
                                    excerpt=text[:MAX_CHAPTER_EXCERPT_CHARS],
                                    why_relevant=scope_text(
                                        interaction_locale,
                                        CopilotTextKey.SCOPE_CHAPTER_MENTIONS_ENTITY,
                                        entity_name=entity.name,
                                    ),
                                )
                            )
            except Exception:
                logger.debug(
                    "Window index load failed, falling back to tail chapters",
                    exc_info=True,
                )

    if len(items) < 3 and snapshot.focus_variant != "whole_book":
        fallback_reason = scope_text(
            interaction_locale, CopilotTextKey.SCOPE_RECENT_CHAPTER_CONTEXT
        )
        if lifecycle and lifecycle.status == WINDOW_INDEX_STATUS_STALE:
            fallback_reason = scope_text(
                interaction_locale, CopilotTextKey.SCOPE_STALE_RECENT_CHAPTER_CONTEXT
            )
        elif lifecycle and lifecycle.status == WINDOW_INDEX_STATUS_MISSING:
            fallback_reason = scope_text(
                interaction_locale, CopilotTextKey.SCOPE_MISSING_RECENT_CHAPTER_CONTEXT
            )
        elif lifecycle and lifecycle.status == WINDOW_INDEX_STATUS_FAILED:
            fallback_reason = scope_text(
                interaction_locale, CopilotTextKey.SCOPE_FAILED_RECENT_CHAPTER_CONTEXT
            )
        chapters = (
            db.query(Chapter)
            .filter(Chapter.novel_id == novel.id)
            .order_by(Chapter.chapter_number.desc())
            .limit(3)
            .all()
        )
        seen_ch_ids = {
            item.source_ref.get("chapter_id")
            for item in items
            if item.source_type == "chapter_excerpt"
        }
        for chapter in chapters:
            if (
                chapter.id in seen_ch_ids
                or not chapter.content
                or not chapter.content.strip()
            ):
                continue
            text = (
                chapter.content[-MAX_CHAPTER_EXCERPT_CHARS:]
                if len(chapter.content) > MAX_CHAPTER_EXCERPT_CHARS
                else chapter.content
            )
            items.append(
                EvidenceItem(
                    evidence_id=f"ch_{chapter.id}_tail",
                    source_type="chapter_excerpt",
                    source_ref={
                        "chapter_id": chapter.id,
                        "chapter_number": chapter.chapter_number,
                        "start_pos": max(
                            0, len(chapter.content) - MAX_CHAPTER_EXCERPT_CHARS
                        ),
                        "end_pos": len(chapter.content),
                    },
                    title=scope_text(
                        interaction_locale,
                        CopilotTextKey.SCOPE_CHAPTER_TAIL_TITLE,
                        chapter_number=chapter.chapter_number,
                    ),
                    excerpt=text[:MAX_CHAPTER_EXCERPT_CHARS],
                    why_relevant=fallback_reason,
                )
            )


def _gather_entity_evidence(
    snapshot: ScopeSnapshot,
    context: dict | None,
    items: list[EvidenceItem],
    interaction_locale: str,
) -> None:
    """Add world-model entity rows as evidence items."""
    target_id = (context or {}).get("entity_id")
    if target_id:
        entity = snapshot.entities_by_id.get(target_id)
        if entity:
            desc = (
                entity.description[:500]
                if entity.description
                else scope_text(
                    interaction_locale,
                    CopilotTextKey.TEXT_NO_DESCRIPTION,
                )
            )
            attrs = snapshot.attributes_by_entity.get(entity.id, [])
            attr_text = "; ".join(
                f"{attr.key}={attr.surface[:80]}" for attr in attrs[:5]
            )
            excerpt = f"{entity.name} ({entity.entity_type}): {desc}"
            if attr_text:
                excerpt = append_scope_labeled_line(
                    excerpt,
                    interaction_locale=interaction_locale,
                    label_key=CopilotTextKey.TEXT_ATTRIBUTES_LABEL,
                    value=attr_text,
                )
            items.append(
                EvidenceItem(
                    evidence_id=f"ent_{entity.id}",
                    source_type="world_entity",
                    source_ref={"entity_id": entity.id},
                    title=scope_text(
                        interaction_locale,
                        CopilotTextKey.SCOPE_ENTITY_TITLE,
                        entity_name=entity.name,
                    ),
                    excerpt=excerpt,
                    why_relevant=scope_text(
                        interaction_locale,
                        CopilotTextKey.SCOPE_ENTITY_TARGET_REASON,
                    ),
                )
            )


def _gather_relationship_evidence(
    snapshot: ScopeSnapshot,
    context: dict | None,
    items: list[EvidenceItem],
    interaction_locale: str,
) -> None:
    """Add relationship rows as evidence for relationship-scoped work."""
    target_id = (context or {}).get("entity_id")
    if not target_id:
        return
    for relationship in snapshot.relationships[:10]:
        if relationship.source_id == target_id or relationship.target_id == target_id:
            source = snapshot.entities_by_id.get(relationship.source_id)
            target = snapshot.entities_by_id.get(relationship.target_id)
            source_name = source.name if source else f"#{relationship.source_id}"
            target_name = target.name if target else f"#{relationship.target_id}"
            description = (
                relationship.description[:200] if relationship.description else ""
            )
            items.append(
                EvidenceItem(
                    evidence_id=f"rel_{relationship.id}",
                    source_type="world_relationship",
                    source_ref={
                        "relationship_id": relationship.id,
                        "source_id": relationship.source_id,
                        "target_id": relationship.target_id,
                    },
                    title=f"{source_name} --[{relationship.label}]--> {target_name}",
                    excerpt=scope_text(
                        interaction_locale,
                        CopilotTextKey.SCOPE_RELATIONSHIP_EXCERPT,
                        source_name=source_name,
                        label=relationship.label,
                        target_name=target_name,
                        description=description,
                    ),
                    why_relevant=scope_text(
                        interaction_locale,
                        CopilotTextKey.SCOPE_RELATIONSHIP_TARGET_REASON,
                    ),
                )
            )


def _gather_draft_row_evidence(
    snapshot: ScopeSnapshot,
    items: list[EvidenceItem],
    interaction_locale: str,
) -> None:
    """Surface draft rows themselves as first-class evidence in draft governance."""
    for entity in snapshot.draft_entities[:6]:
        attrs = snapshot.attributes_by_entity.get(entity.id, [])
        attr_text = "; ".join(f"{attr.key}={attr.surface[:60]}" for attr in attrs[:4])
        excerpt = scope_text(
            interaction_locale,
            CopilotTextKey.SCOPE_DRAFT_ENTITY_EXCERPT,
            entity_name=entity.name,
            entity_type=entity.entity_type,
        )
        if entity.description:
            excerpt = append_scope_labeled_line(
                excerpt,
                interaction_locale=interaction_locale,
                label_key=CopilotTextKey.TEXT_DESCRIPTION_LABEL,
                value=entity.description[:200],
            )
        else:
            excerpt = append_scope_labeled_line(
                excerpt,
                interaction_locale=interaction_locale,
                label_key=CopilotTextKey.TEXT_DESCRIPTION_LABEL,
                value=scope_text(
                    interaction_locale, CopilotTextKey.TEXT_NO_DESCRIPTION
                ),
            )
        if attr_text:
            excerpt = append_scope_labeled_line(
                excerpt,
                interaction_locale=interaction_locale,
                label_key=CopilotTextKey.TEXT_ATTRIBUTES_LABEL,
                value=attr_text,
            )
        items.append(
            EvidenceItem(
                evidence_id=f"draft_ent_{entity.id}",
                source_type="world_entity",
                source_ref={"entity_id": entity.id},
                title=scope_text(
                    interaction_locale,
                    CopilotTextKey.SCOPE_DRAFT_ENTITY_TITLE,
                    entity_name=entity.name,
                ),
                excerpt=excerpt,
                why_relevant=scope_text(
                    interaction_locale,
                    CopilotTextKey.SCOPE_DRAFT_ENTITY_REASON,
                ),
            )
        )

    for relationship in snapshot.draft_relationships[:6]:
        source = snapshot.entities_by_id.get(relationship.source_id)
        target = snapshot.entities_by_id.get(relationship.target_id)
        excerpt = scope_text(
            interaction_locale,
            CopilotTextKey.SCOPE_DRAFT_RELATIONSHIP_EXCERPT,
            source_name=source.name if source else "?",
            label=relationship.label,
            target_name=target.name if target else "?",
        )
        if relationship.description:
            excerpt = append_scope_labeled_line(
                excerpt,
                interaction_locale=interaction_locale,
                label_key=CopilotTextKey.TEXT_DESCRIPTION_LABEL,
                value=relationship.description[:200],
            )
        else:
            excerpt = append_scope_labeled_line(
                excerpt,
                interaction_locale=interaction_locale,
                label_key=CopilotTextKey.TEXT_DESCRIPTION_LABEL,
                value=scope_text(
                    interaction_locale, CopilotTextKey.TEXT_NO_DESCRIPTION
                ),
            )
        items.append(
            EvidenceItem(
                evidence_id=f"draft_rel_{relationship.id}",
                source_type="world_relationship",
                source_ref={
                    "relationship_id": relationship.id,
                    "source_id": relationship.source_id,
                    "target_id": relationship.target_id,
                },
                title=scope_text(
                    interaction_locale,
                    CopilotTextKey.SCOPE_DRAFT_RELATIONSHIP_TITLE,
                    label=relationship.label,
                ),
                excerpt=excerpt,
                why_relevant=scope_text(
                    interaction_locale,
                    CopilotTextKey.SCOPE_DRAFT_RELATIONSHIP_REASON,
                ),
            )
        )

    for system in snapshot.draft_systems[:4]:
        excerpt = scope_text(
            interaction_locale,
            CopilotTextKey.SCOPE_DRAFT_SYSTEM_EXCERPT,
            system_name=system.name,
        )
        if system.description:
            excerpt = append_scope_labeled_line(
                excerpt,
                interaction_locale=interaction_locale,
                label_key=CopilotTextKey.TEXT_DESCRIPTION_LABEL,
                value=system.description[:200],
            )
        items.append(
            EvidenceItem(
                evidence_id=f"draft_sys_{system.id}",
                source_type="world_system",
                source_ref={"system_id": system.id},
                title=scope_text(
                    interaction_locale,
                    CopilotTextKey.SCOPE_DRAFT_SYSTEM_TITLE,
                    system_name=system.name,
                ),
                excerpt=excerpt,
                why_relevant=scope_text(
                    interaction_locale,
                    CopilotTextKey.SCOPE_DRAFT_SYSTEM_REASON,
                ),
            )
        )


def serialize_evidence(evidence: EvidenceItem) -> dict[str, Any]:
    return {
        "evidence_id": evidence.evidence_id,
        "source_type": evidence.source_type,
        "source_ref": evidence.source_ref,
        "title": evidence.title,
        "excerpt": evidence.excerpt,
        "why_relevant": evidence.why_relevant,
        "pack_id": evidence.pack_id,
        "source_refs": evidence.source_refs,
        "anchor_terms": evidence.anchor_terms,
        "support_count": evidence.support_count,
        "preview_excerpt": evidence.preview_excerpt,
        "expanded": evidence.expanded,
    }
