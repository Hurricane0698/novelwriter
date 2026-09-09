# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import hashlib
from bisect import bisect_left, bisect_right
from collections.abc import Iterable, Sequence

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.continuation_text import format_recent_chapters_for_prompt
from app.models import Chapter, NovelContextSummary


def _load_chapters_for_ranges(
    db: Session,
    novel_id: int,
    ranges: Iterable[tuple[int, int]],
) -> list[Chapter]:
    # Merge overlaps without pulling unrelated chapters between distant recaps.
    merged: list[tuple[int, int]] = []
    for start, end in sorted(set(ranges)):
        if end < start:
            continue
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    chapters: list[Chapter] = []
    # Bound SQL expression/parameter counts even for a long recap history.
    for offset in range(0, len(merged), 200):
        chapters.extend(
            db.query(Chapter)
            .filter(
                Chapter.novel_id == novel_id,
                or_(*(
                    Chapter.chapter_number.between(start, end)
                    for start, end in merged[offset:offset + 200]
                )),
            )
            .order_by(Chapter.chapter_number.asc())
            .all()
        )
    return chapters


def load_context_summary_source(
    db: Session,
    *,
    novel_id: int,
    start_chapter: int,
    end_chapter: int,
    locale: str | None,
) -> str:
    """Render the canonical, Markdown-preserving source for a chapter range."""
    chapters = _load_chapters_for_ranges(db, novel_id, [(start_chapter, end_chapter)])
    if not chapters:
        return ""
    return format_recent_chapters_for_prompt(chapters, locale=locale)


def context_summary_source_fingerprint(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _load_source_fingerprints(
    db: Session,
    *,
    novel_id: int,
    ranges: Iterable[tuple[int, int]],
    locale: str | None,
) -> dict[tuple[int, int], str | None]:
    unique_ranges = set(ranges)
    chapters = _load_chapters_for_ranges(db, novel_id, unique_ranges)
    numbers = [chapter.chapter_number for chapter in chapters]
    rendered = [
        format_recent_chapters_for_prompt([chapter], locale=locale).encode("utf-8")
        for chapter in chapters
    ]
    fingerprints: dict[tuple[int, int], str | None] = {}
    for start, end in unique_ranges:
        first = bisect_left(numbers, start)
        last = bisect_right(numbers, end)
        if first >= last:
            fingerprints[(start, end)] = None
            continue
        digest = hashlib.sha256()
        for index in range(first, last):
            if index > first:
                # Match format_recent_chapters_for_prompt's chapter separator
                # without allocating each overlapping full-range source again.
                digest.update(b"\n\n")
            digest.update(rendered[index])
        fingerprints[(start, end)] = digest.hexdigest()
    return fingerprints


def inspect_context_summary_staleness(
    db: Session,
    *,
    novel_id: int,
    summaries: Sequence[NovelContextSummary],
    locale: str | None,
) -> dict[int, bool]:
    fingerprints = _load_source_fingerprints(
        db,
        novel_id=novel_id,
        ranges=((row.start_chapter, row.end_chapter) for row in summaries),
        locale=locale,
    )
    return {
        row.id: (
            fingerprints[(row.start_chapter, row.end_chapter)] is None
            or fingerprints[(row.start_chapter, row.end_chapter)] != row.source_fingerprint
        )
        for row in summaries
    }


def is_context_summary_stale(
    db: Session,
    *,
    novel_id: int,
    start_chapter: int,
    end_chapter: int,
    source_fingerprint: str,
    locale: str | None,
) -> bool:
    fingerprints = _load_source_fingerprints(
        db,
        novel_id=novel_id,
        ranges=[(start_chapter, end_chapter)],
        locale=locale,
    )
    current = fingerprints[(start_chapter, end_chapter)]
    return current is None or current != source_fingerprint
