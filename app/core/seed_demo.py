# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Seed a demo novel (西游记 前27回) for a newly registered user.

Called once per user at invite-registration time.  The function is
idempotent per user: if the user already owns a novel titled "西游记",
no duplicate is created.

Assets required (committed to repo):
  - data/demo/西游记_前27回.txt
  - data/worldpacks/journey-to-the-west.json
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.parser import parse_novel_file
from app.models import Chapter, Novel, User

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_TXT = REPO_ROOT / "data" / "demo" / "西游记_前27回.txt"
DEMO_WORLDPACK = REPO_ROOT / "data" / "worldpacks" / "journey-to-the-west.json"

DEMO_TITLE = "西游记"
DEMO_AUTHOR = "吴承恩"


def seed_demo_novel(db: Session, user: User) -> int | None:
    """Create the demo novel + import worldpack for *user*.

    Returns the novel id on success, or None if skipped/failed.
    """
    # Idempotency: skip if user already has the demo novel.
    existing = (
        db.query(Novel.id)
        .filter(Novel.owner_id == user.id, Novel.title == DEMO_TITLE)
        .first()
    )
    if existing is not None:
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
    db.flush()  # get novel.id before inserting chapters

    for chapter_num, chapter_title, chapter_content in chapters:
        db.add(Chapter(
            novel_id=novel.id,
            chapter_number=chapter_num,
            title=chapter_title,
            content=chapter_content,
        ))
    db.flush()

    # Commit novel + chapters first so the worldpack import (which also
    # commits internally) operates on a consistent novel row.
    db.commit()

    # Import worldpack via the same logic as the API endpoint.
    try:
        from app.api.world import import_worldpack_v1
        from app.schemas import WorldpackV1Payload

        raw = json.loads(DEMO_WORLDPACK.read_text(encoding="utf-8"))
        payload = WorldpackV1Payload(**raw)
        import_worldpack_v1(
            novel_id=novel.id,
            body=payload,
            db=db,
            current_user=user,
        )
    except Exception:
        logger.exception("seed_demo: worldpack import failed (novel %s)", novel.id)
    logger.info(
        "seed_demo: created novel %s (%d chapters) for user %s",
        novel.id,
        len(chapters),
        user.username,
    )
    return novel.id
