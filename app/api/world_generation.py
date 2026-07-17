# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.world_support import run_world_operation_async
from app.core.auth import get_current_user_or_default
from app.core.llm_request import get_llm_config
from app.core.llm_config import ResolvedLlmConfig
from app.core.world.generation_application import generate_world_from_text as generate_world_from_text_use_case
from app.database import get_db
from app.models import User
from app.schemas import WorldGenerateRequest, WorldGenerateResponse

router = APIRouter()


@router.post("/generate", response_model=WorldGenerateResponse)
async def generate_world_from_text(
    novel_id: int,
    body: WorldGenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
    llm_config: ResolvedLlmConfig = Depends(get_llm_config),
):
    return await run_world_operation_async(
        generate_world_from_text_use_case,
        novel_id,
        text=body.text,
        db=db,
        current_user=current_user,
        llm_config=llm_config,
        request_id=getattr(getattr(request, "state", None), "request_id", None),
    )


__all__ = ["generate_world_from_text", "router"]
