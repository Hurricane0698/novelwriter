# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings, resolve_context_chapters
from app.core.chapter_numbering import load_recent_chapters
from app.core.context_assembly import apply_writer_context_budget, assemble_writer_context
from app.core.continuation_text import (
    append_user_instruction_for_relevance,
    extract_narrative_constraints,
    format_recent_chapters_for_prompt,
    format_world_context_for_prompt,
)
from app.models import User
from app.schemas import ContinueDebugSummary, ContinueRequest

from . import novel_support

logger = logging.getLogger(__name__)


def _build_continue_debug_summary(
    writer_ctx: dict[str, Any],
    context_chapters: int,
) -> ContinueDebugSummary:
    systems = writer_ctx.get("systems") or []
    entities = writer_ctx.get("entities") or []
    relationships = writer_ctx.get("relationships") or []
    debug = writer_ctx.get("debug") or {}

    def _safe_int(value: Any) -> int | None:
        try:
            if value is None:
                return None
            return int(value)
        except Exception:
            return None

    entity_names = [str(e.get("name") or "").strip() for e in entities if str(e.get("name") or "").strip()]
    system_names = [str(s.get("name") or "").strip() for s in systems if str(s.get("name") or "").strip()]

    id_to_name: dict[int, str] = {}
    for entity in entities:
        entity_id = _safe_int(entity.get("id"))
        name = str(entity.get("name") or "").strip()
        if entity_id is None or not name:
            continue
        id_to_name[entity_id] = name

    rel_names: list[str] = []
    for relationship in relationships:
        label = str(relationship.get("label") or "").strip()
        src_raw = relationship.get("source_id")
        tgt_raw = relationship.get("target_id")
        src_id = _safe_int(src_raw)
        tgt_id = _safe_int(tgt_raw)
        src = id_to_name.get(src_id, str(src_raw)) if src_id is not None else "?"
        tgt = id_to_name.get(tgt_id, str(tgt_raw)) if tgt_id is not None else "?"
        if label:
            rel_names.append(f"{src} --{label}--> {tgt}")
        else:
            rel_names.append(f"{src} --> {tgt}")

    relevant_entity_ids: list[int] = []
    for raw in list(debug.get("relevant_entity_ids") or []):
        entity_id = _safe_int(raw)
        if entity_id is not None:
            relevant_entity_ids.append(entity_id)

    return ContinueDebugSummary(
        context_chapters=int(context_chapters),
        injected_systems=system_names,
        injected_entities=entity_names,
        injected_relationships=rel_names,
        relevant_entity_ids=relevant_entity_ids,
        ambiguous_keywords_disabled=list(debug.get("ambiguous_keywords_disabled") or []),
    )


@dataclass
class _ContinuationContext:
    recent_text: str
    world_context: str
    narrative_constraints: str
    debug_summary: ContinueDebugSummary
    writer_ctx: dict[str, Any]
    effective_context_chapters: int
    novel_language: str | None = None


def _prepare_continuation_context(
    db: Session,
    novel_id: int,
    req: ContinueRequest,
    current_user: User,
) -> _ContinuationContext:
    settings = get_settings()

    novel = novel_support.get_accessible_novel(db, novel_id, current_user)

    effective_context_chapters = resolve_context_chapters(
        req.context_chapters,
        default=settings.max_context_chapters,
    )

    recent_chapters = load_recent_chapters(db, novel_id, effective_context_chapters)
    if not recent_chapters:
        raise HTTPException(status_code=400, detail="Novel has no chapters")

    novel_language = getattr(novel, "language", None)
    recent_text = format_recent_chapters_for_prompt(recent_chapters, locale=novel_language)
    relevance_text = append_user_instruction_for_relevance(recent_text, req.prompt, locale=novel_language)

    try:
        writer_ctx = assemble_writer_context(db, novel_id, chapter_text=relevance_text)
        writer_ctx = apply_writer_context_budget(writer_ctx)
    except Exception:
        logger.exception("assemble_writer_context failed for novel %s", novel_id)
        raise HTTPException(status_code=500, detail="Context assembly failed")

    world_context = format_world_context_for_prompt(writer_ctx, locale=novel_language)
    narrative_constraints = extract_narrative_constraints(writer_ctx)
    debug_summary = _build_continue_debug_summary(
        writer_ctx,
        context_chapters=effective_context_chapters,
    )

    return _ContinuationContext(
        recent_text=recent_text,
        world_context=world_context,
        narrative_constraints=narrative_constraints,
        debug_summary=debug_summary,
        writer_ctx=writer_ctx,
        effective_context_chapters=effective_context_chapters,
        novel_language=novel_language,
    )
