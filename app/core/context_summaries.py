# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from app.core.continuation_text import format_recent_chapters_for_prompt
from app.models import Chapter


def load_context_summary_source(
    db: Session,
    *,
    novel_id: int,
    start_chapter: int,
    end_chapter: int,
    locale: str | None,
) -> str:
    """Render the canonical, Markdown-preserving source for a chapter range."""
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
        return ""
    return format_recent_chapters_for_prompt(chapters, locale=locale)


def context_summary_source_fingerprint(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def is_context_summary_stale(
    db: Session,
    *,
    novel_id: int,
    start_chapter: int,
    end_chapter: int,
    source_fingerprint: str,
    locale: str | None,
) -> bool:
    source = load_context_summary_source(
        db,
        novel_id=novel_id,
        start_chapter=start_chapter,
        end_chapter=end_chapter,
        locale=locale,
    )
    return not source or context_summary_source_fingerprint(source) != source_fingerprint
