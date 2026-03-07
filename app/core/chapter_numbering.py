# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from sqlalchemy.orm import Session

from app.models import Chapter


def get_next_missing_chapter_number(db: Session, novel_id: int) -> int:
    """Return the smallest missing positive chapter_number for a novel.

    Examples:
      - existing {1,2,3} -> 4
      - existing {1,3}   -> 2
    """
    rows = (
        db.query(Chapter.chapter_number)
        .filter(Chapter.novel_id == novel_id)
        .order_by(Chapter.chapter_number.asc())
        .all()
    )
    expected = 1
    for (num,) in rows:
        if num is None or num < 1:
            continue
        if num == expected:
            expected += 1
            continue
        if num > expected:
            break
    return expected
