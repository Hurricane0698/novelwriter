# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Seed a demo novel (西游记 前27回) for a newly registered user."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.indexing.lifecycle import (
    enqueue_window_index_rebuild_job,
    mark_window_index_inputs_changed,
)
from app.core.parser import parse_novel_file
from app.core.world.worldpack_import import import_worldpack_payload
from app.models import Chapter, Novel, User

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_DATA_DIR = REPO_ROOT / "data" / "demo"
DEMO_TXT = DEMO_DATA_DIR / "西游记_前27回.txt"
DEMO_WORLDPACK = REPO_ROOT / "data" / "worldpacks" / "journey-to-the-west.json"

DEMO_TITLE = "西游记"
DEMO_AUTHOR = "吴承恩"


def is_seeded_demo_file_path(file_path: str | None) -> bool:
    if not file_path:
        return False
    try:
        return Path(file_path).resolve(strict=False).is_relative_to(
            DEMO_DATA_DIR.resolve(strict=False)
        )
    except Exception:
        return False


def is_seeded_demo_novel(novel: Novel | None) -> bool:
    return is_seeded_demo_file_path(getattr(novel, "file_path", None))


def _enqueue_demo_window_index_build(db: Session, *, novel: Novel) -> None:
    try:
        target_revision = mark_window_index_inputs_changed(novel)
        enqueue_window_index_rebuild_job(
            db,
            novel_id=novel.id,
            target_revision=target_revision,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(novel)


def seed_demo_novel(db: Session, user: User) -> int | None:
    """Create the demo novel + import worldpack for *user*."""
    existing_file_paths = (
        db.query(Novel.file_path)
        .filter(Novel.owner_id == user.id)
        .all()
    )
    if any(is_seeded_demo_file_path(file_path) for (file_path,) in existing_file_paths):
        return None

    if not DEMO_TXT.exists():
        logger.warning("seed_demo: txt asset missing: %s", DEMO_TXT)
        return None
    if not DEMO_WORLDPACK.exists():
        logger.warning("seed_demo: worldpack asset missing: %s", DEMO_WORLDPACK)
        return None

    try:
        chapters = parse_novel_file(str(DEMO_TXT))
    except Exception:
        logger.exception("seed_demo: failed to parse demo txt")
        return None

    novel = Novel(
        title=DEMO_TITLE,
        author=DEMO_AUTHOR,
        file_path=str(DEMO_TXT),
        total_chapters=len(chapters),
        owner_id=user.id,
    )
    db.add(novel)
    db.flush()

    for chapter_number, parsed_chapter in enumerate(chapters, start=1):
        db.add(
            Chapter(
                novel_id=novel.id,
                chapter_number=chapter_number,
                title=parsed_chapter.title,
                source_chapter_label=parsed_chapter.source_chapter_label,
                source_chapter_number=parsed_chapter.source_chapter_number,
                content=parsed_chapter.content,
            )
        )
    db.flush()
    db.commit()

    try:
        from app.schemas import WorldpackV1Payload

        raw = json.loads(DEMO_WORLDPACK.read_text(encoding="utf-8"))
        payload = WorldpackV1Payload(**raw)
        import_worldpack_payload(novel_id=novel.id, body=payload, db=db)
    except Exception:
        logger.exception("seed_demo: worldpack import failed (novel %s)", novel.id)

    _enqueue_demo_window_index_build(db, novel=novel)

    logger.info(
        "seed_demo: created novel %s (%d chapters) for user %s",
        novel.id,
        len(chapters),
        user.username,
    )
    return novel.id
