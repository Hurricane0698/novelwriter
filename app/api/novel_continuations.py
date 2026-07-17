# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_or_default
from app.core.llm_request import get_llm_config
from app.core.llm_config import ResolvedLlmConfig
from app.database import get_db
from app.models import Continuation, User
from app.schemas import (
    ContinueRequest,
    ContinueResponse,
    ContinuationResponse,
)

from . import novel_support
from . import novel_continuation_runtime as continuation_runtime

router = APIRouter(prefix="/api/novels", tags=["novels"])


@router.post("/{novel_id}/continue", response_model=ContinueResponse)
async def continue_novel_endpoint(
    novel_id: int,
    req: ContinueRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
    llm_config: ResolvedLlmConfig = Depends(get_llm_config),
):
    return await continuation_runtime.handle_continue_request(
        db=db,
        novel_id=novel_id,
        req=req,
        request=request,
        current_user=current_user,
        llm_config=llm_config,
    )


@router.post("/{novel_id}/continue/stream")
async def continue_novel_stream_endpoint(
    novel_id: int,
    req: ContinueRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
    llm_config: ResolvedLlmConfig = Depends(get_llm_config),
):
    return await continuation_runtime.handle_continue_stream_request(
        db=db,
        novel_id=novel_id,
        req=req,
        request=request,
        current_user=current_user,
        llm_config=llm_config,
    )


@router.get("/{novel_id}/continuations", response_model=List[ContinuationResponse])
def get_continuations(
    novel_id: int,
    ids: str = Query(..., description="Comma-separated continuation IDs"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    novel_support.get_accessible_novel(db, novel_id, current_user)

    parts = [p.strip() for p in (ids or "").split(",") if p.strip()]
    if not parts:
        raise HTTPException(status_code=400, detail="ids must not be empty")
    try:
        wanted = [int(p) for p in parts]
    except ValueError:
        raise HTTPException(status_code=400, detail="ids must be a comma-separated list of integers")
    if len(wanted) > 10:
        raise HTTPException(status_code=400, detail="Too many ids")

    rows = (
        db.query(Continuation)
        .filter(Continuation.novel_id == novel_id, Continuation.id.in_(wanted))
        .all()
    )
    by_id = {c.id: c for c in rows}
    missing = [i for i in wanted if i not in by_id]
    if missing:
        raise HTTPException(status_code=404, detail="Continuation not found")
    return [by_id[i] for i in wanted]
