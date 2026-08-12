from __future__ import annotations

from sqlalchemy.orm import Session

from app.content_formats import NovelContentFormat
from app.language import DEFAULT_LANGUAGE
from app.models import Novel

from .parser_service import resolve_requested_language
from .job_store import enqueue_novel_ingest_job


def accept_novel_upload(
    db: Session,
    *,
    title: str,
    author: str,
    file_path: str,
    owner_id: int | None,
    source_bytes: int,
    requested_language: str | None,
    content_format: NovelContentFormat,
) -> Novel:
    normalized_requested_language = resolve_requested_language(requested_language)
    novel = Novel(
        title=title,
        author=author,
        language=normalized_requested_language or DEFAULT_LANGUAGE,
        file_path=file_path,
        content_format=content_format,
        total_chapters=0,
        owner_id=owner_id,
    )
    db.add(novel)
    db.flush()
    enqueue_novel_ingest_job(
        db,
        novel_id=int(novel.id),
        source_bytes=source_bytes,
        requested_language=normalized_requested_language,
    )
    return novel
