# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_or_default
from app.core.ingest import inspect_novel_readinesses
from app.core.indexing.lifecycle import inspect_window_index_lifecycles
from app.database import get_db
from app.language import normalize_language_code
from app.models import Chapter, Novel, User
from app.schemas import NovelCreate, NovelResponse, NovelTitle, WindowIndexStateResponse

from . import novel_support

router = APIRouter(prefix="/api/novels", tags=["novels"])


@router.post("", response_model=NovelResponse, status_code=201)
def create_novel(
    data: NovelCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    novel = Novel(
        title=data.title, language=normalize_language_code(data.language),
        owner_id=current_user.id, file_path="", total_chapters=1,
        chapters=[Chapter(chapter_number=1, content="")],
    )
    db.add(novel)
    db.commit()
    return novel_support.serialize_novel_with_states(novel, db=db, has_window_index_payload=False)


@router.patch("/{novel_id}", response_model=NovelResponse)
def rename_novel(novel_id: int, data: NovelTitle, db: Session = Depends(get_db)):
    novel = novel_support.get_novel(db, novel_id)
    novel.title = data.title
    db.commit()
    return novel_support.serialize_novel_with_states(
        novel, db=db, has_window_index_payload=novel.window_index_payload_size is not None,
    )


@router.get("", response_model=List[NovelResponse], dependencies=[Depends(get_current_user_or_default)])
def list_novels(
    db: Session = Depends(get_db),
):
    novels = db.query(Novel).order_by(Novel.created_at.desc()).all()
    index_states = inspect_window_index_lifecycles(
        novels,
        db=db,
        has_payload_overrides={
            novel.id: novel.window_index_payload_size is not None
            for novel in novels
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
):
    novel = novel_support.get_novel(db, novel_id)
    return novel_support.serialize_novel_with_states(
        novel,
        db=db,
        has_window_index_payload=novel.window_index_payload_size is not None,
    )


@router.get("/{novel_id}/status", response_model=WindowIndexStateResponse)
def get_novel_status(
    novel_id: int,
    db: Session = Depends(get_db),
):
    novel = novel_support.get_novel(db, novel_id)
    return novel_support.serialize_novel_with_states(
        novel,
        db=db,
        has_window_index_payload=novel.window_index_payload_size is not None,
    ).window_index
