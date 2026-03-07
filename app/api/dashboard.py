# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""
Dashboard API - Aggregated endpoints for frontend

Provides aggregated data to reduce multiple API calls from frontend:
- GET /api/novels/{id}/dashboard - Full novel dashboard
- POST /api/novels/{id}/lorebook/entries/batch - Batch create lorebook entries
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Novel,
    Chapter,
    LoreEntry,
)
from app.schemas import (
    NovelDashboard,
    OrchestrationStatusSummary,
    ComponentStatus,
    RecentChapterSummary,
    LoreEntryBatchCreate,
    LoreEntryBatchResponse,
    LoreEntryResponse,
)
from app.api.deps import verify_novel_access

router = APIRouter(
    prefix="/api/novels/{novel_id}",
    tags=["dashboard"],
    dependencies=[Depends(verify_novel_access)],
)


def _get_novel_or_404(db: Session, novel_id: int) -> Novel:
    """Get novel by ID or raise 404."""
    novel = db.get(Novel, novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail=f"Novel {novel_id} not found")
    return novel


# =============================================================================
# Dashboard Endpoint
# =============================================================================

@router.get("/dashboard", response_model=NovelDashboard)
async def get_novel_dashboard(
    novel_id: int,
    recent_chapters_limit: int = 5,
    db: Session = Depends(get_db),
):
    """
    Get aggregated dashboard data for a novel.

    Returns all data needed for a novel overview page in a single request:
    - Basic novel info
    - Component status (lorebook)
    - Recent chapters
    """
    novel = _get_novel_or_404(db, novel_id)

    # Build component status
    lorebook_count = db.query(func.count(LoreEntry.id)).filter(
        LoreEntry.novel_id == novel_id,
        LoreEntry.enabled.is_(True),
    ).scalar() or 0

    status = OrchestrationStatusSummary(
        lorebook=ComponentStatus(ready=lorebook_count > 0, count=lorebook_count),
    )

    # Get recent chapters
    recent_chapters_db = (
        db.query(Chapter)
        .filter(Chapter.novel_id == novel_id)
        .order_by(Chapter.chapter_number.desc())
        .limit(recent_chapters_limit)
        .all()
    )
    recent_chapters = [
        RecentChapterSummary(
            chapter_number=ch.chapter_number,
            title=ch.title,
            char_count=len(ch.content) if ch.content else 0,
        )
        for ch in reversed(recent_chapters_db)
    ]

    return NovelDashboard(
        novel_id=novel.id,
        title=novel.title,
        author=novel.author,
        total_chapters=novel.total_chapters,
        status=status,
        recent_chapters=recent_chapters,
    )


# =============================================================================
# Batch Operations
# =============================================================================

@router.post("/lorebook/entries/batch", response_model=LoreEntryBatchResponse, status_code=201)
async def batch_create_lorebook_entries(
    novel_id: int,
    request: LoreEntryBatchCreate,
    db: Session = Depends(get_db),
):
    """
    Batch create lorebook entries.

    Creates multiple lorebook entries in a single request.
    Entries that fail validation are skipped and reported in errors.
    """
    import uuid
    from app.models import LoreEntry, LoreKey

    _get_novel_or_404(db, novel_id)

    created_entries: List[LoreEntry] = []
    errors: List[str] = []

    for i, entry_data in enumerate(request.entries):
        try:
            entry = LoreEntry(
                novel_id=novel_id,
                uid=str(uuid.uuid4()),
                title=entry_data.title,
                content=entry_data.content,
                entry_type=entry_data.entry_type.value,
                token_budget=entry_data.token_budget,
                priority=entry_data.priority,
                enabled=True,
            )
            db.add(entry)
            db.flush()  # Get the ID

            for kw in entry_data.keywords:
                key = LoreKey(
                    entry_id=entry.id,
                    keyword=kw.keyword,
                    is_regex=kw.is_regex,
                    case_sensitive=kw.case_sensitive,
                )
                db.add(key)

            created_entries.append(entry)
        except Exception as e:
            errors.append(f"Entry {i} ({entry_data.title}): {str(e)}")

    db.commit()

    # Refresh to get relationships
    for entry in created_entries:
        db.refresh(entry)

    return LoreEntryBatchResponse(
        created=len(created_entries),
        entries=[LoreEntryResponse.model_validate(e) for e in created_entries],
        errors=errors,
    )
