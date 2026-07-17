# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, defer

from app.core.auth import get_current_user_or_default
from app.core.events import ensure_project_start_event
from app.core.ingest import inspect_novel_readinesses
from app.core.indexing.lifecycle import inspect_window_index_lifecycles
from app.core.seed_demo import is_seeded_demo_novel
from app.database import get_db
from app.models import Novel, User
from app.schemas import NovelResponse, WindowIndexStateResponse

from . import novel_support

router = APIRouter(prefix="/api/novels", tags=["novels"])


@router.get("", response_model=List[NovelResponse])
def list_novels(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    rows = (
        novel_support.user_novels(db, current_user)
        .options(defer(Novel.window_index))
        .add_columns(novel_support.novel_window_index_presence_column())
        .order_by(Novel.created_at.desc())
        .all()
    )
    novels = [novel for novel, _ in rows]
    index_states = inspect_window_index_lifecycles(
        novels,
        db=db,
        has_payload_overrides={
            novel.id: bool(has_window_index_payload)
            for novel, has_window_index_payload in rows
            if isinstance(getattr(novel, "id", None), int)
        },
    )
    readiness_states = inspect_novel_readinesses(
        novels,
        db=db,
        index_states=index_states,
    )
    return [
        novel_support.serialize_novel(
            novel,
            index_state=index_states.get(novel.id),
            readiness_state=readiness_states.get(novel.id),
        )
        for novel in novels
    ]


@router.get("/{novel_id}", response_model=NovelResponse)
def get_novel(
    novel_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    novel, has_payload = novel_support.fetch_novel_with_presence(db, novel_id, current_user)
    if is_seeded_demo_novel(novel):
        ensure_project_start_event(
            db,
            user_id=current_user.id,
            novel_id=novel_id,
            start_mode="demo",
            meta={"entry_action": "demo_open"},
        )
    return novel_support.serialize_novel_with_states(
        novel,
        db=db,
        has_window_index_payload=has_payload,
    )


@router.get("/{novel_id}/status", response_model=WindowIndexStateResponse)
def get_novel_status(
    novel_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    novel, has_payload = novel_support.fetch_novel_with_presence(db, novel_id, current_user)
    return novel_support.serialize_novel_with_states(
        novel,
        db=db,
        has_window_index_payload=has_payload,
    ).window_index
