"""Small, replaceable provenance for current world values."""

from __future__ import annotations

from copy import deepcopy
from sqlalchemy.orm import Session

from app.models import Chapter
from app.core.text_targets import content_hash


def describe_sources(row, db: Session | None) -> list[dict]:
    metadata = row.source_metadata or {}
    values_changed = any(
        getattr(row, key, None) != value
        for key, value in metadata.get("values", {}).items()
    )
    result = []
    for source in metadata.get("refs", [])[:3]:
        item = deepcopy(source)
        chapter = (
            db.get(Chapter, item.get("chapter_id"))
            if db is not None and item.get("chapter_id")
            else None
        )
        if chapter is None:
            item["status"] = "missing" if db is not None else "needs_review"
        elif values_changed or content_hash(chapter.content) != item.get(
            "content_hash"
        ):
            item["status"] = "needs_review"
        else:
            item["status"] = "current"
        result.append(item)
    return result
