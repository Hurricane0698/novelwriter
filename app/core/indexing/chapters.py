from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Chapter

from .builder import ChapterText


def load_chapter_texts(db: Session, novel_id: int) -> list[ChapterText]:
    rows = (
        db.query(Chapter.id, Chapter.content)
        .filter(Chapter.novel_id == novel_id)
        .order_by(Chapter.chapter_number.asc())
        .all()
    )
    return [
        ChapterText(chapter_id=chapter_id, text=content or "")
        for chapter_id, content in rows
        if (content or "").strip()
    ]


def has_non_empty_chapter_text(db: Session, novel_id: int) -> bool:
    """Existence check with Python `.strip()` semantics.

    Streams rows and short-circuits on the first non-blank chapter instead of
    materializing the whole book, so trigger-time guards stay cheap.
    """
    rows = (
        db.query(Chapter.content)
        .filter(
            Chapter.novel_id == novel_id,
            Chapter.content.isnot(None),
            Chapter.content != "",
        )
        .yield_per(20)
    )
    return any((content or "").strip() for (content,) in rows)
