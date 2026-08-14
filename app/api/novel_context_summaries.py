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
from app.core.context_summaries import (
    context_summary_source_fingerprint,
    is_context_summary_stale,
    load_context_summary_source,
)
from app.core.llm_config import ResolvedLlmConfig
from app.core.llm_request import get_llm_config
from app.core.llm_semaphore import acquire_llm_slot, release_llm_slot
from app.database import get_db
from app.language import resolve_prompt_locale
from app.models import Chapter, NovelContextSummary, User
from app.schemas import (
    NovelContextSummaryCreateRequest,
    NovelContextSummaryResponse,
    NovelContextSummaryUpdateRequest,
)

from . import novel_support

router = APIRouter(
    prefix="/api/novels/{novel_id}/context-summaries",
    tags=["novel-context-summaries"],
)
logger = logging.getLogger(__name__)


def _error_detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _load_source(
    db: Session,
    *,
    novel_id: int,
    start_chapter: int,
    end_chapter: int,
    locale: str,
) -> tuple[str, str]:
    settings = get_settings()
    range_size = end_chapter - start_chapter + 1
    if range_size > settings.context_summary_max_range_chapters:
        raise HTTPException(
            status_code=422,
            detail=_error_detail(
                "context_summary_range_too_large",
                f"Select at most {settings.context_summary_max_range_chapters} chapters per recap.",
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
            detail=_error_detail(
                "context_summary_source_empty",
                "The novel has no chapters to summarize.",
            ),
        )
    if end_chapter > int(last_chapter):
        raise HTTPException(
            status_code=422,
            detail=_error_detail(
                "context_summary_range_invalid",
                f"Chapter range must be within 1-{int(last_chapter)}.",
            ),
        )

    source = load_context_summary_source(
        db,
        novel_id=novel_id,
        start_chapter=start_chapter,
        end_chapter=end_chapter,
        locale=locale,
    )
    if not source:
        raise HTTPException(
            status_code=422,
            detail=_error_detail(
                "context_summary_source_empty",
                "The selected chapter range has no content.",
            ),
        )
    if len(source) > settings.context_summary_source_max_chars:
        raise HTTPException(
            status_code=422,
            detail=_error_detail(
                "context_summary_source_too_large",
                "The selected chapters are too long for one recap. Choose a smaller range.",
            ),
        )
    return source, context_summary_source_fingerprint(source)


def _summary_prompt(
    *,
    locale: str,
    novel_title: str,
    start_chapter: int,
    end_chapter: int,
    source: str,
) -> tuple[str, str]:
    if locale.lower().startswith("zh"):
        prompt = f"""请回顾小说《{novel_title}》第{start_chapter}章到第{end_chapter}章已经发生的剧情。
这是用户手动指定的正文范围。不要改变范围，不要预测后续剧情，也不要补写材料中不存在的内容。
请输出结构清晰的纯文本回顾，包含主要事件与因果、人物状态变化、重要线索或伏笔、已确立的世界信息，以及范围结束时尚未解决的问题。
不要写续写正文，不要输出 JSON。

正文材料：
{source}"""
        return prompt, "你是严谨的小说剧情编辑，只根据提供的正文回顾已经发生的内容。"

    prompt = f"""Recap what has already happened in chapters {start_chapter} through {end_chapter} of “{novel_title}”.
This source range was selected explicitly by the user. Do not change it, predict future plot, or invent facts absent from the source.
Return a structured plain-text recap covering causal events, character-state changes, important clues or foreshadowing, established world facts, and unresolved issues at the end of the range.
Do not write continuation prose and do not return JSON.

Source chapters:
{source}"""
    return prompt, "You are a rigorous fiction editor. Recap only what the supplied chapters establish."


def _summary_title(locale: str, start_chapter: int, end_chapter: int) -> str:
    if locale.lower().startswith("zh"):
        return f"第{start_chapter}—{end_chapter}章远期剧情回顾"
    return f"Chapters {start_chapter}–{end_chapter} recap"


def _is_stale(db: Session, row: NovelContextSummary, locale: str | None) -> bool:
    return is_context_summary_stale(
        db,
        novel_id=int(row.novel_id),
        start_chapter=int(row.start_chapter),
        end_chapter=int(row.end_chapter),
        source_fingerprint=str(row.source_fingerprint),
        locale=locale,
    )


def _response(row: NovelContextSummary, *, is_stale: bool) -> dict[str, object]:
    return {
        "id": row.id,
        "novel_id": row.novel_id,
        "start_chapter": row.start_chapter,
        "end_chapter": row.end_chapter,
        "title": row.title,
        "content": row.content,
        "model": row.model,
        "review_status": row.review_status,
        "is_stale": is_stale,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _get_summary(db: Session, *, novel_id: int, summary_id: int) -> NovelContextSummary:
    row = (
        db.query(NovelContextSummary)
        .filter(
            NovelContextSummary.id == summary_id,
            NovelContextSummary.novel_id == novel_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=_error_detail("context_summary_not_found", "Context summary not found."),
        )
    return row


async def _generate_and_persist(
    *,
    db: Session,
    row: NovelContextSummary | None,
    novel_id: int,
    novel_title: str,
    start_chapter: int,
    end_chapter: int,
    locale: str,
    current_user: User,
    llm_config: ResolvedLlmConfig,
) -> NovelContextSummary:
    source, source_fingerprint = _load_source(
        db,
        novel_id=novel_id,
        start_chapter=start_chapter,
        end_chapter=end_chapter,
        locale=locale,
    )
    prompt, system_prompt = _summary_prompt(
        locale=locale,
        novel_title=novel_title,
        start_chapter=start_chapter,
        end_chapter=end_chapter,
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
            max_tokens=get_settings().context_summary_generation_max_tokens,
            temperature=0.2,
            role="summary",
            user_id=current_user.id,
        )
        normalized_content = content.strip()
        if not normalized_content:
            raise HTTPException(
                status_code=502,
                detail=_error_detail(
                    "context_summary_generation_empty",
                    "Context summary generation returned no content.",
                ),
            )

        if row is None:
            row = NovelContextSummary(
                novel_id=novel_id,
                start_chapter=start_chapter,
                end_chapter=end_chapter,
                title=_summary_title(locale, start_chapter, end_chapter),
                content=normalized_content,
                model=llm_config.model,
                source_fingerprint=source_fingerprint,
                review_status="draft",
            )
            db.add(row)
        else:
            row.title = _summary_title(locale, start_chapter, end_chapter)
            row.content = normalized_content
            row.model = llm_config.model
            row.source_fingerprint = source_fingerprint
            row.review_status = "draft"

        db.flush()
        quota.charge(1)
        db.commit()
        db.refresh(row)
        return row
    except HTTPException:
        db.rollback()
        raise
    except LLMUnavailableError as exc:
        db.rollback()
        logger.warning("context summary generation LLM unavailable", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail=_error_detail(
                "context_summary_generation_llm_unavailable",
                "The AI model is temporarily unavailable.",
            ),
        ) from exc
    except Exception as exc:
        db.rollback()
        logger.exception("context summary generation failed for novel %s", novel_id)
        raise HTTPException(
            status_code=500,
            detail=_error_detail(
                "context_summary_generation_failed",
                "Context summary generation failed.",
            ),
        ) from exc
    finally:
        if quota_reserved:
            quota.finalize()
        if slot_acquired:
            release_llm_slot()


@router.get("", response_model=list[NovelContextSummaryResponse])
def list_context_summaries(
    novel_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    novel = novel_support.get_accessible_novel(db, novel_id, current_user)
    rows = (
        db.query(NovelContextSummary)
        .filter(NovelContextSummary.novel_id == novel_id)
        .order_by(
            NovelContextSummary.start_chapter.asc(),
            NovelContextSummary.end_chapter.asc(),
            NovelContextSummary.created_at.desc(),
        )
        .all()
    )
    return [_response(row, is_stale=_is_stale(db, row, novel.language)) for row in rows]


@router.post("", response_model=NovelContextSummaryResponse, status_code=201)
async def create_context_summary(
    novel_id: int,
    req: NovelContextSummaryCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
    llm_config: ResolvedLlmConfig = Depends(get_llm_config),
):
    novel = novel_support.get_accessible_novel(db, novel_id, current_user)
    locale = resolve_prompt_locale(novel_language=novel.language)
    row = await _generate_and_persist(
        db=db,
        row=None,
        novel_id=novel_id,
        novel_title=novel.title,
        start_chapter=req.start_chapter,
        end_chapter=req.end_chapter,
        locale=locale,
        current_user=current_user,
        llm_config=llm_config,
    )
    return _response(row, is_stale=False)


@router.put("/{summary_id}", response_model=NovelContextSummaryResponse)
def update_context_summary(
    novel_id: int,
    summary_id: int,
    req: NovelContextSummaryUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    novel = novel_support.get_accessible_novel(db, novel_id, current_user)
    row = _get_summary(db, novel_id=novel_id, summary_id=summary_id)
    stale = _is_stale(db, row, novel.language)
    if req.review_status == "confirmed" and stale:
        raise HTTPException(
            status_code=409,
            detail=_error_detail(
                "context_summary_stale",
                "The source chapters changed. Regenerate this recap before confirming it.",
            ),
        )
    row.content = req.content
    row.review_status = req.review_status
    try:
        db.commit()
        db.refresh(row)
    except Exception:
        db.rollback()
        raise
    return _response(row, is_stale=stale)


@router.post("/{summary_id}/regenerate", response_model=NovelContextSummaryResponse)
async def regenerate_context_summary(
    novel_id: int,
    summary_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
    llm_config: ResolvedLlmConfig = Depends(get_llm_config),
):
    novel = novel_support.get_accessible_novel(db, novel_id, current_user)
    row = _get_summary(db, novel_id=novel_id, summary_id=summary_id)
    locale = resolve_prompt_locale(novel_language=novel.language)
    row = await _generate_and_persist(
        db=db,
        row=row,
        novel_id=novel_id,
        novel_title=novel.title,
        start_chapter=row.start_chapter,
        end_chapter=row.end_chapter,
        locale=locale,
        current_user=current_user,
        llm_config=llm_config,
    )
    return _response(row, is_stale=False)


@router.delete("/{summary_id}")
def delete_context_summary(
    novel_id: int,
    summary_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    novel_support.get_accessible_novel(db, novel_id, current_user)
    row = _get_summary(db, novel_id=novel_id, summary_id=summary_id)
    db.delete(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"deleted": True, "id": summary_id}
