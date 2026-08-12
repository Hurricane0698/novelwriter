# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.ai_client import AIClient, LLMUnavailableError
from app.core.auth import QuotaScope, ensure_ai_available, get_current_user_or_default
from app.core.continuation_text import format_recent_chapters_for_prompt
from app.core.llm_config import ResolvedLlmConfig
from app.core.llm_request import get_llm_config
from app.core.llm_semaphore import acquire_llm_slot, release_llm_slot
from app.database import get_db
from app.language import resolve_prompt_locale
from app.models import Chapter, NovelOutline, User
from app.schemas import NovelOutlineCreateRequest, NovelOutlineResponse

from . import novel_support

router = APIRouter(prefix="/api/novels/{novel_id}/outlines", tags=["novel-outlines"])
logger = logging.getLogger(__name__)


def _error_detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _load_range_text(
    db: Session,
    *,
    novel_id: int,
    start_chapter: int,
    end_chapter: int,
    locale: str,
) -> str:
    settings = get_settings()
    range_size = end_chapter - start_chapter + 1
    if range_size > settings.outline_max_range_chapters:
        raise HTTPException(
            status_code=422,
            detail=_error_detail(
                "outline_range_too_large",
                f"Select at most {settings.outline_max_range_chapters} chapters per outline.",
            ),
        )

    last_chapter = (
        db.query(func.max(Chapter.chapter_number))
        .filter(Chapter.novel_id == novel_id)
        .scalar()
    )
    if last_chapter is None:
        raise HTTPException(
            status_code=422,
            detail=_error_detail("outline_source_empty", "The novel has no chapters to summarize."),
        )
    if end_chapter > int(last_chapter):
        raise HTTPException(
            status_code=422,
            detail=_error_detail(
                "outline_range_invalid",
                f"Chapter range must be within 1-{int(last_chapter)}.",
            ),
        )

    chapters = (
        db.query(Chapter)
        .filter(
            Chapter.novel_id == novel_id,
            Chapter.chapter_number >= start_chapter,
            Chapter.chapter_number <= end_chapter,
        )
        .order_by(Chapter.chapter_number.asc())
        .all()
    )
    if not chapters:
        raise HTTPException(
            status_code=422,
            detail=_error_detail(
                "outline_source_empty",
                "The selected chapter range has no content.",
            ),
        )

    source = format_recent_chapters_for_prompt(chapters, locale=locale)
    if len(source) > settings.outline_source_max_chars:
        raise HTTPException(
            status_code=422,
            detail=_error_detail(
                "outline_source_too_large",
                "The selected chapters are too long for one outline. Choose a smaller range.",
            ),
        )
    return source


def _outline_prompt(
    *,
    locale: str,
    novel_title: str,
    start_chapter: int,
    end_chapter: int,
    source: str,
) -> tuple[str, str]:
    if locale.lower().startswith("zh"):
        prompt = f"""请总结小说《{novel_title}》第{start_chapter}章到第{end_chapter}章的剧情大纲。
这是用户手动指定的范围。不要改变范围，也不要补写材料中不存在的内容。
请输出结构清晰的纯文本大纲，包含主要事件与因果、人物状态变化、重要线索或伏笔、世界观信息，以及范围结束时尚未解决的问题。
不要写续写正文，不要输出 JSON。

正文材料：
{source}"""
        return prompt, "你是严谨的小说剧情编辑，只根据提供的正文做准确总结。"

    prompt = f"""Summarize chapters {start_chapter} through {end_chapter} of “{novel_title}”.
This range was selected explicitly by the user. Do not change it or invent facts absent from the source.
Return a structured plain-text outline covering causal events, character-state changes, important clues or foreshadowing, world facts, and unresolved issues at the end of the range.
Do not write continuation prose and do not return JSON.

Source chapters:
{source}"""
    return prompt, "You are a rigorous fiction editor. Summarize only what the supplied chapters establish."


def _outline_title(locale: str, start_chapter: int, end_chapter: int) -> str:
    if locale.lower().startswith("zh"):
        return f"第{start_chapter}—{end_chapter}章剧情大纲"
    return f"Chapters {start_chapter}–{end_chapter} outline"


@router.get("", response_model=list[NovelOutlineResponse])
def list_outlines(
    novel_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    novel_support.get_accessible_novel(db, novel_id, current_user)
    return (
        db.query(NovelOutline)
        .filter(NovelOutline.novel_id == novel_id)
        .order_by(
            NovelOutline.start_chapter.asc(),
            NovelOutline.end_chapter.asc(),
            NovelOutline.created_at.desc(),
        )
        .all()
    )


@router.post("", response_model=NovelOutlineResponse, status_code=201)
async def create_outline(
    novel_id: int,
    req: NovelOutlineCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
    llm_config: ResolvedLlmConfig = Depends(get_llm_config),
):
    novel = novel_support.get_accessible_novel(db, novel_id, current_user)
    prompt_locale = resolve_prompt_locale(novel_language=novel.language)
    source = _load_range_text(
        db,
        novel_id=novel_id,
        start_chapter=req.start_chapter,
        end_chapter=req.end_chapter,
        locale=prompt_locale,
    )
    prompt, system_prompt = _outline_prompt(
        locale=prompt_locale,
        novel_title=novel.title,
        start_chapter=req.start_chapter,
        end_chapter=req.end_chapter,
        source=source,
    )

    ensure_ai_available(db, billing_source=llm_config.billing_source_hint)
    quota = QuotaScope(db, current_user.id, count=1)
    slot_acquired = False
    quota_reserved = False
    try:
        await acquire_llm_slot()
        slot_acquired = True
        quota.reserve()
        quota_reserved = True
        content = await AIClient().generate(
            prompt,
            llm_config=llm_config,
            system_prompt=system_prompt,
            max_tokens=get_settings().outline_generation_max_tokens,
            temperature=0.2,
            role="summary",
            user_id=current_user.id,
        )
        normalized_content = content.strip()
        if not normalized_content:
            raise HTTPException(
                status_code=502,
                detail=_error_detail(
                    "outline_generation_empty",
                    "Outline generation returned no content.",
                ),
            )

        row = NovelOutline(
            novel_id=novel_id,
            start_chapter=req.start_chapter,
            end_chapter=req.end_chapter,
            title=_outline_title(prompt_locale, req.start_chapter, req.end_chapter),
            content=normalized_content,
            model=llm_config.model,
        )
        db.add(row)
        db.flush()
        quota.charge(1)
        db.commit()
        db.refresh(row)
    except HTTPException:
        db.rollback()
        raise
    except LLMUnavailableError as exc:
        db.rollback()
        logger.warning("outline generation LLM unavailable", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail=_error_detail(
                "outline_generation_llm_unavailable",
                "The AI model is temporarily unavailable.",
            ),
        ) from exc
    except Exception as exc:
        db.rollback()
        logger.exception("outline generation failed for novel %s", novel_id)
        raise HTTPException(
            status_code=500,
            detail=_error_detail("outline_generation_failed", "Outline generation failed."),
        ) from exc
    finally:
        if quota_reserved:
            quota.finalize()
        if slot_acquired:
            release_llm_slot()

    return row


@router.delete("/{outline_id}")
def delete_outline(
    novel_id: int,
    outline_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    novel_support.get_accessible_novel(db, novel_id, current_user)
    row = (
        db.query(NovelOutline)
        .filter(NovelOutline.id == outline_id, NovelOutline.novel_id == novel_id)
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=_error_detail("outline_not_found", "Outline not found."),
        )
    db.delete(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"deleted": True, "id": outline_id}
