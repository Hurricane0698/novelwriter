# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.content_formats import MARKDOWN_CONTENT_FORMAT
from app.core.auth import get_current_user_or_default
from app.core.chapter_numbering import get_next_missing_chapter_number
from app.core.events import record_event
from app.core.indexing.lifecycle import (
    enqueue_window_index_rebuild_job,
    mark_window_index_inputs_changed,
)
from app.core.markdown_parser import validate_markdown_chapter_body
from app.core.source_errors import MarkdownStructureInvalidError
from app.database import get_db
from app.models import Chapter, Novel, User
from app.schemas import (
    ChapterCreateRequest,
    ChapterMetaResponse,
    ChapterResponse,
    ChapterUpdateRequest,
)

from . import novel_support

router = APIRouter(prefix="/api/novels", tags=["novels"])


def _get_chapter_or_404(db: Session, novel_id: int, chapter_number: int) -> Chapter:
    chapter = (
        db.query(Chapter)
        .filter(Chapter.novel_id == novel_id, Chapter.chapter_number == chapter_number)
        .first()
    )
    if not chapter:
        raise HTTPException(
            status_code=404,
            detail=f"Chapter {chapter_number} not found in novel {novel_id}",
        )
    return chapter


def _persist_new_chapter(db: Session, novel: Novel, novel_id: int) -> None:
    """Flush the pending chapter, bump counters, and enqueue the index rebuild.

    Runs inside the caller's try block; IntegrityError propagates to the
    caller's numbering-specific conflict handler.
    """
    db.flush()
    novel.total_chapters = int(novel.total_chapters or 0) + 1
    target_revision = mark_window_index_inputs_changed(novel)
    enqueue_window_index_rebuild_job(
        db,
        novel_id=novel_id,
        target_revision=target_revision,
    )
    db.commit()


def _source_volume_for_new_chapter(
    db: Session,
    *,
    novel: Novel,
    chapter_number: int,
) -> str | None:
    if novel.content_format != MARKDOWN_CONTENT_FORMAT:
        return None
    previous = (
        db.query(Chapter.source_volume_title)
        .filter(
            Chapter.novel_id == novel.id,
            Chapter.chapter_number < chapter_number,
        )
        .order_by(Chapter.chapter_number.desc())
        .first()
    )
    return previous[0] if previous is not None else None


def _validate_chapter_content(novel: Novel, content: str) -> None:
    if novel.content_format != MARKDOWN_CONTENT_FORMAT:
        return
    try:
        validate_markdown_chapter_body(content)
    except MarkdownStructureInvalidError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "markdown_chapter_body_invalid",
                "message": str(exc),
            },
        ) from exc


@router.get("/{novel_id}/chapters", response_model=List[ChapterResponse])
def get_chapters(
    novel_id: int,
    skip: int = 0,
    limit: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
) -> List[ChapterResponse]:
    novel_support.get_accessible_novel(db, novel_id, current_user)

    query = (
        db.query(Chapter)
        .filter(Chapter.novel_id == novel_id)
        .order_by(Chapter.chapter_number)
        .offset(skip)
    )
    if limit is not None:
        query = query.limit(limit)
    return query.all()


@router.get("/{novel_id}/chapters/meta", response_model=List[ChapterMetaResponse])
def get_chapters_meta(
    novel_id: int,
    skip: int = 0,
    limit: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
) -> List[ChapterMetaResponse]:
    novel_support.get_accessible_novel(db, novel_id, current_user)

    query = (
        db.query(
            Chapter.id,
            Chapter.novel_id,
            Chapter.chapter_number,
            Chapter.title,
            Chapter.source_chapter_label,
            Chapter.source_chapter_number,
            Chapter.source_volume_title,
            Chapter.created_at,
        )
        .filter(Chapter.novel_id == novel_id)
        .order_by(Chapter.chapter_number)
        .offset(skip)
    )
    if limit is not None:
        query = query.limit(limit)
    rows = query.all()
    return [
        ChapterMetaResponse(
            id=r.id,
            novel_id=r.novel_id,
            chapter_number=r.chapter_number,
            title=r.title,
            source_chapter_label=r.source_chapter_label,
            source_chapter_number=r.source_chapter_number,
            source_volume_title=r.source_volume_title,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/{novel_id}/chapters/{chapter_number}", response_model=ChapterResponse)
def get_chapter(
    novel_id: int,
    chapter_number: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    novel_support.get_accessible_novel(db, novel_id, current_user)

    return _get_chapter_or_404(db, novel_id, chapter_number)


@router.post("/{novel_id}/chapters", response_model=ChapterResponse, status_code=201)
def create_chapter(
    novel_id: int,
    req: ChapterCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    novel = novel_support.get_accessible_novel(db, novel_id, current_user)
    _validate_chapter_content(novel, req.content)

    if req.chapter_number is not None and req.chapter_number < 1:
        raise HTTPException(status_code=400, detail="chapter_number must be >= 1")

    if req.chapter_number is None:
        for attempt in range(3):
            chapter_number = get_next_missing_chapter_number(db, novel_id)
            chapter = Chapter(
                novel_id=novel_id,
                chapter_number=chapter_number,
                title=req.title,
                source_volume_title=_source_volume_for_new_chapter(
                    db,
                    novel=novel,
                    chapter_number=chapter_number,
                ),
                content=req.content,
            )
            db.add(chapter)
            try:
                _persist_new_chapter(db, novel, novel_id)
            except IntegrityError:
                db.rollback()
                try:
                    db.expunge(chapter)
                except Exception:
                    pass
                db.refresh(novel)
                if attempt < 2:
                    continue
                raise HTTPException(
                    status_code=409,
                    detail="Chapter number conflict; please retry",
                )

            db.refresh(chapter)
            record_event(db, current_user.id, "chapter_save", novel_id=novel_id, meta={"chapter": chapter_number})
            return chapter

        raise HTTPException(status_code=409, detail="Chapter number conflict; please retry")

    chapter_number = req.chapter_number
    existing = (
        db.query(Chapter)
        .filter(Chapter.novel_id == novel_id, Chapter.chapter_number == chapter_number)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"Chapter {chapter_number} already exists")

    chapter = Chapter(
        novel_id=novel_id,
        chapter_number=chapter_number,
        title=req.title,
        source_volume_title=_source_volume_for_new_chapter(
            db,
            novel=novel,
            chapter_number=chapter_number,
        ),
        content=req.content,
    )
    db.add(chapter)
    try:
        _persist_new_chapter(db, novel, novel_id)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Chapter {chapter_number} already exists")

    db.refresh(chapter)
    record_event(db, current_user.id, "chapter_save", novel_id=novel_id, meta={"chapter": chapter_number})
    return chapter


@router.put("/{novel_id}/chapters/{chapter_number}", response_model=ChapterResponse)
def update_chapter(
    novel_id: int,
    chapter_number: int,
    req: ChapterUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    novel = novel_support.get_accessible_novel(db, novel_id, current_user)

    chapter = _get_chapter_or_404(db, novel_id, chapter_number)

    if req.title is None and req.content is None:
        raise HTTPException(status_code=400, detail="Must provide title and/or content")

    if req.content is not None:
        _validate_chapter_content(novel, req.content)
    if req.title is not None:
        chapter.title = req.title
    if req.content is not None:
        chapter.content = req.content
    target_revision = mark_window_index_inputs_changed(novel)
    enqueue_window_index_rebuild_job(
        db,
        novel_id=novel_id,
        target_revision=target_revision,
    )
    db.commit()
    db.refresh(chapter)
    record_event(db, current_user.id, "chapter_save", novel_id=novel_id, meta={"chapter": chapter_number})
    return chapter


@router.delete("/{novel_id}/chapters/{chapter_number}", status_code=204)
def delete_chapter(
    novel_id: int,
    chapter_number: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    novel = novel_support.get_accessible_novel(db, novel_id, current_user)

    chapter = _get_chapter_or_404(db, novel_id, chapter_number)

    db.delete(chapter)
    novel.total_chapters = max(int(novel.total_chapters or 0) - 1, 0)
    target_revision = mark_window_index_inputs_changed(novel)
    enqueue_window_index_rebuild_job(
        db,
        novel_id=novel_id,
        target_revision=target_revision,
    )
    db.commit()
    return Response(status_code=204)
