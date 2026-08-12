from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.indexing.lifecycle import (
    enqueue_window_index_rebuild_job,
    mark_window_index_inputs_changed,
    mark_window_index_missing,
)
from app.core.indexing.planner import should_enqueue_window_index_build_immediately
from app.models import Chapter, Novel, NovelIngestJob

from .contracts import IngestPolicyDecision, ParsedNovelIngest


def replace_novel_chapters(
    db: Session,
    *,
    novel_id: int,
    chapters,
) -> None:
    db.query(Chapter).filter(Chapter.novel_id == novel_id).delete(synchronize_session=False)
    for chapter_number, parsed_chapter in enumerate(chapters, start=1):
        db.add(
            Chapter(
                novel_id=novel_id,
                chapter_number=chapter_number,
                title=parsed_chapter.title,
                source_chapter_label=parsed_chapter.source_chapter_label,
                source_chapter_number=parsed_chapter.source_chapter_number,
                source_volume_title=parsed_chapter.source_volume_title,
                content=parsed_chapter.content,
            )
        )


def persist_ingest_success(
    db: Session,
    *,
    novel: Novel,
    job: NovelIngestJob,
    parsed: ParsedNovelIngest,
    decision: IngestPolicyDecision,
) -> None:
    replace_novel_chapters(db, novel_id=int(novel.id), chapters=parsed.chapters)
    novel.language = parsed.resolved_language
    novel.total_chapters = len(parsed.chapters)

    if parsed.chapters:
        target_revision = mark_window_index_inputs_changed(novel)
        if should_enqueue_window_index_build_immediately(decision.auto_index_plan):
            enqueue_window_index_rebuild_job(
                db,
                novel_id=int(novel.id),
                target_revision=target_revision,
            )
    else:
        mark_window_index_missing(novel, revision=0)

    job.size_tier = decision.size_tier
    job.auto_index_plan = decision.auto_index_plan
    job.bootstrap_plan = decision.bootstrap_plan
    job.readiness_mode = decision.readiness_mode
    job.source_chars = int(parsed.source_chars)
    job.chapter_count = len(parsed.chapters)
    job.resolved_language = parsed.resolved_language
