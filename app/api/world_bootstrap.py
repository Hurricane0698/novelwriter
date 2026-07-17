# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.world_support import run_world_operation, run_world_operation_async, serialize_bootstrap_job
from app.config import get_settings
from app.core.auth import get_current_user_or_default
from app.core.llm_request import get_llm_config
from app.core.world.bootstrap_application import (
    get_bootstrap_status as get_bootstrap_status_use_case,
    trigger_bootstrap as trigger_bootstrap_use_case,
)
from app.database import get_db
from app.models import User
from app.schemas import BootstrapJobResponse, BootstrapTriggerRequest

router = APIRouter()


@router.post("/bootstrap", response_model=BootstrapJobResponse, status_code=202)
async def trigger_bootstrap(
    novel_id: int,
    llm_config: dict | None = Depends(get_llm_config),
    body: BootstrapTriggerRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    job = await run_world_operation_async(
        trigger_bootstrap_use_case,
        novel_id,
        body=body,
        db=db,
        current_user=current_user,
        llm_config=llm_config,
        settings=get_settings(),
    )
    return serialize_bootstrap_job(job)


@router.get("/bootstrap/status", response_model=BootstrapJobResponse)
def get_bootstrap_status(
    novel_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _ = current_user
    job = run_world_operation(
        get_bootstrap_status_use_case,
        novel_id,
        db=db,
        settings=get_settings(),
    )
    return serialize_bootstrap_job(job)


__all__ = ["get_bootstrap_status", "router", "trigger_bootstrap"]
