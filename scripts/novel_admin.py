#!/usr/bin/env python3
"""
Small maintenance helper for the SQLite novels DB.

This script is intentionally dependency-light (stdlib + SQLAlchemy already in the repo).

Typical uses:
  - Deduplicate accidental re-uploads that created duplicate Novel rows.
  - Sync a Novel's Chapter rows from its on-disk .txt file (parse_novel_file()).

Note: This script does NOT fetch/crawl chapter content from the internet.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

# When invoked as `python scripts/...`, Python's sys.path[0] becomes `scripts/`,
# so ensure the repo root is importable.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import create_engine, select, func  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.parser import parse_novel_file  # noqa: E402
from app.models import (  # noqa: E402
    Novel,
    Chapter,
    WorldRelationship,
    WorldEntity,
    WorldEntityAttribute,
    LoreEntry,
    LoreKey,
    Outline,
    Continuation,
    WorldSystem,
    BootstrapJob,
)


def _db_url(db_path: Path) -> str:
    return f"sqlite:///{db_path}"


def _delete_novel_rows(db: Session, *, novel_id: int) -> None:
    """
    Best-effort cascade delete for rows that depend on a Novel.
    We do explicit deletes instead of relying on ORM relationship cascades,
    so we don't need to load thousands of rows into memory.
    """
    # World graph
    db.query(WorldRelationship).filter(WorldRelationship.novel_id == novel_id).delete(synchronize_session=False)

    entity_ids = [
        entity_id
        for (entity_id,) in db.query(WorldEntity.id).filter(WorldEntity.novel_id == novel_id).all()
    ]
    if entity_ids:
        db.query(WorldEntityAttribute).filter(WorldEntityAttribute.entity_id.in_(entity_ids)).delete(
            synchronize_session=False
        )
    db.query(WorldEntity).filter(WorldEntity.novel_id == novel_id).delete(synchronize_session=False)
    db.query(WorldSystem).filter(WorldSystem.novel_id == novel_id).delete(synchronize_session=False)

    # Lorebook
    lore_entry_ids = [
        entry_id for (entry_id,) in db.query(LoreEntry.id).filter(LoreEntry.novel_id == novel_id).all()
    ]
    if lore_entry_ids:
        db.query(LoreKey).filter(LoreKey.entry_id.in_(lore_entry_ids)).delete(synchronize_session=False)
    db.query(LoreEntry).filter(LoreEntry.novel_id == novel_id).delete(synchronize_session=False)

    # Writing artifacts
    db.query(Outline).filter(Outline.novel_id == novel_id).delete(synchronize_session=False)
    db.query(Continuation).filter(Continuation.novel_id == novel_id).delete(synchronize_session=False)

    # Chapters
    db.query(Chapter).filter(Chapter.novel_id == novel_id).delete(synchronize_session=False)

    # Jobs
    db.query(BootstrapJob).filter(BootstrapJob.novel_id == novel_id).delete(synchronize_session=False)

    # Finally the novel row
    db.query(Novel).filter(Novel.id == novel_id).delete(synchronize_session=False)


def cmd_dedupe(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    engine = create_engine(_db_url(db_path))

    with Session(engine) as db:
        q = select(Novel).where(Novel.title == args.title)
        if args.file_path:
            q = q.where(Novel.file_path == str(Path(args.file_path).resolve()))
        novels = db.execute(q).scalars().all()
        if not novels:
            print("No matching novels found.")
            return 1

        keep_id = args.keep_id
        if keep_id is None:
            # Prefer the one with more world graph rows (tends to be the active one),
            # otherwise the newest (largest id).
            scored: list[tuple[int, int]] = []
            for n in novels:
                score = 0
                score += db.execute(
                    select(func.count()).select_from(WorldEntity).where(WorldEntity.novel_id == n.id)
                ).scalar_one()
                score += db.execute(
                    select(func.count()).select_from(WorldRelationship).where(WorldRelationship.novel_id == n.id)
                ).scalar_one()
                score += db.execute(
                    select(func.count()).select_from(BootstrapJob).where(BootstrapJob.novel_id == n.id)
                ).scalar_one()
                scored.append((n.id, score))
            scored.sort(key=lambda t: (t[1], t[0]), reverse=True)
            keep_id = scored[0][0]

        keep = next((n for n in novels if n.id == keep_id), None)
        if keep is None:
            print(f"--keep-id {keep_id} is not in the matching set.")
            return 2

        to_delete = [n for n in novels if n.id != keep.id]
        if not to_delete:
            print(f"No duplicates to delete. Kept novel_id={keep.id}.")
            return 0
        delete_ids = [n.id for n in to_delete]

        if args.dry_run:
            print(f"Would keep novel_id={keep.id} and delete: {delete_ids}")
            return 0

        for n in to_delete:
            _delete_novel_rows(db, novel_id=n.id)
        db.commit()

        print(f"Kept novel_id={keep.id}. Deleted duplicates: {delete_ids}")
        return 0


def cmd_sync_chapters(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    engine = create_engine(_db_url(db_path))

    with Session(engine) as db:
        novel = db.get(Novel, args.novel_id)
        if novel is None:
            print(f"Novel not found: {args.novel_id}")
            return 1

        file_path = Path(novel.file_path)
        if not file_path.exists():
            print(f"Novel file not found on disk: {file_path}")
            return 2

        parsed = parse_novel_file(str(file_path))
        parsed_total = len(parsed)
        print(f"Parsed chapters from file: {parsed_total}")

        existing = {
            ch.chapter_number: ch
            for ch in db.execute(select(Chapter).where(Chapter.novel_id == novel.id)).scalars().all()
        }

        seen_numbers: set[int] = set()
        inserted = 0
        updated = 0

        for chapter_num, title, content in parsed:
            seen_numbers.add(chapter_num)
            ch = existing.get(chapter_num)
            if ch is None:
                db.add(
                    Chapter(
                        novel_id=novel.id,
                        chapter_number=int(chapter_num),
                        title=str(title or "").strip(),
                        content=str(content or "").strip(),
                    )
                )
                inserted += 1
            else:
                new_title = str(title or "").strip()
                new_content = str(content or "").strip()
                if ch.title != new_title or ch.content != new_content:
                    ch.title = new_title
                    ch.content = new_content
                    updated += 1

        deleted = 0
        for num, ch in existing.items():
            if num not in seen_numbers:
                db.delete(ch)
                deleted += 1

        novel.total_chapters = parsed_total
        db.commit()

        print(
            f"Sync done for novel_id={novel.id}. inserted={inserted} updated={updated} deleted={deleted} "
            f"total_chapters={novel.total_chapters}"
        )
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", default="data/novels.db", help="Path to sqlite db (default: data/novels.db)")

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_dedupe = sub.add_parser("dedupe", help="Delete duplicate Novel rows (same title and optionally same file_path)")
    p_dedupe.add_argument("--title", required=True)
    p_dedupe.add_argument("--file-path", default=None, help="Optional: only consider this file_path")
    p_dedupe.add_argument("--keep-id", type=int, default=None, help="Novel id to keep (default: auto pick)")
    p_dedupe.add_argument("--dry-run", action="store_true")
    p_dedupe.set_defaults(func=cmd_dedupe)

    p_sync = sub.add_parser("sync-chapters", help="Sync Chapter rows from the Novel's file_path on disk")
    p_sync.add_argument("--novel-id", type=int, required=True)
    p_sync.set_defaults(func=cmd_sync_chapters)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
