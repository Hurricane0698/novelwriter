# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""
Lorebook API endpoints for CRUD operations and context injection.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models import Novel, LoreEntry, LoreKey
from app.schemas import (
    LoreEntryCreate,
    LoreEntryUpdate,
    LoreEntryResponse,
    LoreKeyCreate,
    LoreKeyResponse,
    LoreInjectionResponse,
    LoreMatchResult,
)
from app.core.lore_manager import LoreManager
from app.core.character_parser import (
    parse_character_card,
    build_character_content,
    extract_character_keywords,
)
from app.core.cache import cache_manager
from app.config import get_settings
from app.api.deps import verify_novel_access

router = APIRouter(
    prefix="/api/novels/{novel_id}/lorebook",
    tags=["lorebook"],
    dependencies=[Depends(verify_novel_access)],
)


def get_novel_or_404(novel_id: int, db: Session) -> Novel:
    """Get novel by ID or raise 404."""
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if not novel:
        raise HTTPException(
            status_code=404,
            detail=f"Novel with id={novel_id} not found. Verify the novel exists."
        )
    return novel


@router.get("/entries", response_model=List[LoreEntryResponse])
def list_lore_entries(
    novel_id: int,
    enabled_only: bool = False,
    db: Session = Depends(get_db),
):
    """List all lorebook entries for a novel."""
    get_novel_or_404(novel_id, db)

    query = db.query(LoreEntry).filter(LoreEntry.novel_id == novel_id)
    if enabled_only:
        query = query.filter(LoreEntry.enabled.is_(True))

    entries = query.order_by(LoreEntry.priority).all()
    return entries


@router.post("/entries", response_model=LoreEntryResponse, status_code=201)
def create_lore_entry(
    novel_id: int,
    entry_data: LoreEntryCreate,
    db: Session = Depends(get_db),
):
    """Create a new lorebook entry with keywords."""
    get_novel_or_404(novel_id, db)

    if not entry_data.keywords:
        raise HTTPException(
            status_code=400,
            detail="At least one keyword is required. Keywords trigger context injection."
        )

    entry = LoreEntry(
        novel_id=novel_id,
        uid=LoreManager.generate_uid(),
        title=entry_data.title,
        content=entry_data.content,
        entry_type=entry_data.entry_type.value,
        token_budget=entry_data.token_budget,
        priority=entry_data.priority,
        enabled=True,
    )
    db.add(entry)
    db.flush()

    for kw_data in entry_data.keywords:
        key = LoreKey(
            entry_id=entry.id,
            keyword=kw_data.keyword,
            is_regex=kw_data.is_regex,
            case_sensitive=kw_data.case_sensitive,
        )
        db.add(key)

    db.commit()
    db.refresh(entry)
    cache_manager.invalidate_novel(novel_id)
    return entry


@router.post("/entries/import/character-card", response_model=LoreEntryResponse, status_code=201)
async def import_character_card(
    novel_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Import a character card (JSON/PNG) as a lorebook entry."""
    get_novel_or_404(novel_id, db)

    if not file.filename:
        raise HTTPException(status_code=400, detail="Character card filename is required.")

    max_size = 10 * 1024 * 1024
    content = await file.read(max_size + 1)
    if len(content) > max_size:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 10 MB.")
    if not content:
        raise HTTPException(status_code=400, detail="Character card file is empty.")

    try:
        card = parse_character_card(content, file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    name = card.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Character card missing name.")

    card_content = build_character_content(card)
    if not card_content:
        card_content = f"Character: {name}"

    settings = get_settings()
    entry = LoreEntry(
        novel_id=novel_id,
        uid=LoreManager.generate_uid(),
        title=name,
        content=card_content,
        entry_type="Character",
        token_budget=settings.lore_default_token_budget,
        priority=settings.lore_default_priority,
        enabled=True,
    )
    db.add(entry)
    db.flush()

    keywords = extract_character_keywords(card)
    if not keywords:
        keywords = [name]

    for keyword in keywords:
        key = LoreKey(
            entry_id=entry.id,
            keyword=keyword,
            is_regex=False,
            case_sensitive=False,
        )
        db.add(key)

    db.commit()
    db.refresh(entry)
    cache_manager.invalidate_novel(novel_id)
    return entry


@router.get("/entries/{entry_id}", response_model=LoreEntryResponse)
def get_lore_entry(
    novel_id: int,
    entry_id: int,
    db: Session = Depends(get_db),
):
    """Get a specific lorebook entry."""
    get_novel_or_404(novel_id, db)

    entry = db.query(LoreEntry).filter(
        LoreEntry.id == entry_id,
        LoreEntry.novel_id == novel_id,
    ).first()

    if not entry:
        raise HTTPException(
            status_code=404,
            detail=f"Lore entry with id={entry_id} not found in novel {novel_id}."
        )
    return entry


@router.patch("/entries/{entry_id}", response_model=LoreEntryResponse)
def update_lore_entry(
    novel_id: int,
    entry_id: int,
    update_data: LoreEntryUpdate,
    db: Session = Depends(get_db),
):
    """Update a lorebook entry."""
    get_novel_or_404(novel_id, db)

    entry = db.query(LoreEntry).filter(
        LoreEntry.id == entry_id,
        LoreEntry.novel_id == novel_id,
    ).first()

    if not entry:
        raise HTTPException(
            status_code=404,
            detail=f"Lore entry with id={entry_id} not found in novel {novel_id}."
        )

    update_dict = update_data.model_dump(exclude_unset=True)
    if "entry_type" in update_dict and update_dict["entry_type"]:
        update_dict["entry_type"] = update_dict["entry_type"].value

    for field, value in update_dict.items():
        setattr(entry, field, value)

    db.commit()
    db.refresh(entry)
    cache_manager.invalidate_novel(novel_id)
    return entry


@router.delete("/entries/{entry_id}", status_code=204)
def delete_lore_entry(
    novel_id: int,
    entry_id: int,
    db: Session = Depends(get_db),
):
    """Delete a lorebook entry and its keywords."""
    get_novel_or_404(novel_id, db)

    entry = db.query(LoreEntry).filter(
        LoreEntry.id == entry_id,
        LoreEntry.novel_id == novel_id,
    ).first()

    if not entry:
        raise HTTPException(
            status_code=404,
            detail=f"Lore entry with id={entry_id} not found in novel {novel_id}."
        )

    db.delete(entry)
    db.commit()
    cache_manager.invalidate_novel(novel_id)


@router.post("/entries/{entry_id}/keywords", response_model=LoreKeyResponse, status_code=201)
def add_keyword(
    novel_id: int,
    entry_id: int,
    keyword_data: LoreKeyCreate,
    db: Session = Depends(get_db),
):
    """Add a keyword to a lorebook entry."""
    get_novel_or_404(novel_id, db)

    entry = db.query(LoreEntry).filter(
        LoreEntry.id == entry_id,
        LoreEntry.novel_id == novel_id,
    ).first()

    if not entry:
        raise HTTPException(
            status_code=404,
            detail=f"Lore entry with id={entry_id} not found in novel {novel_id}."
        )

    key = LoreKey(
        entry_id=entry.id,
        keyword=keyword_data.keyword,
        is_regex=keyword_data.is_regex,
        case_sensitive=keyword_data.case_sensitive,
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    cache_manager.invalidate_novel(novel_id)
    return key


@router.delete("/entries/{entry_id}/keywords/{keyword_id}", status_code=204)
def delete_keyword(
    novel_id: int,
    entry_id: int,
    keyword_id: int,
    db: Session = Depends(get_db),
):
    """Delete a keyword from a lorebook entry."""
    get_novel_or_404(novel_id, db)

    key = (
        db.query(LoreKey)
        .join(LoreEntry, LoreEntry.id == LoreKey.entry_id)
        .filter(
            LoreKey.id == keyword_id,
            LoreKey.entry_id == entry_id,
            LoreEntry.novel_id == novel_id,
        )
        .first()
    )

    if not key:
        raise HTTPException(
            status_code=404,
            detail=f"Keyword with id={keyword_id} not found in entry {entry_id}."
        )

    remaining_keywords = db.query(LoreKey).filter(
        LoreKey.entry_id == entry_id,
        LoreKey.id != keyword_id,
    ).count()

    if remaining_keywords == 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete the last keyword. Each entry must have at least one keyword."
        )

    db.delete(key)
    db.commit()
    cache_manager.invalidate_novel(novel_id)


@router.post("/match", response_model=LoreInjectionResponse)
def match_and_inject(
    novel_id: int,
    text: str,
    max_tokens: int = None,
    db: Session = Depends(get_db),
):
    """
    Match keywords in text and return injectable context.

    This endpoint scans the provided text for lorebook keywords
    and returns the combined context from matching entries,
    respecting token budgets and priorities.
    """
    get_novel_or_404(novel_id, db)

    lore_manager = LoreManager(novel_id)
    lore_manager.build_automaton(db)
    context, matched_entries, total_tokens = lore_manager.get_injection_context(
        text, max_tokens=max_tokens
    )

    return LoreInjectionResponse(
        context=context,
        matched_entries=[LoreMatchResult(**e) for e in matched_entries],
        total_tokens=total_tokens,
    )
