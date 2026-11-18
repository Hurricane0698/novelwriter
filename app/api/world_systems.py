# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.world import crud
from app.database import get_db
from app.models import WorldSystem
from app.schemas import (
    BatchConfirmRequest,
    BatchConfirmResponse,
    BatchRejectRequest,
    BatchRejectResponse,
    SystemDisplayType,
    WorldOrigin,
    WorldSystemCreate,
    WorldSystemResponse,
    WorldSystemUpdate,
)
from app.api.world_support import (
    WorldModelRowStatus,
    apply_exact_filters,
    apply_ilike_search,
    get_novel,
    get_system as load_world_system,
    parse_visibility_filter,
    run_world_operation,
)

router = APIRouter()


@router.get("/systems", response_model=List[WorldSystemResponse])
def list_systems(
    novel_id: int,
    q: Optional[str] = None,
    origin: Optional[WorldOrigin] = None,
    worldpack_pack_id: Optional[str] = None,
    visibility: Optional[str] = None,
    status: Optional[WorldModelRowStatus] = None,
    display_type: Optional[SystemDisplayType] = None,
    db: Session = Depends(get_db),
):
    get_novel(novel_id, db)
    query = db.query(WorldSystem).filter(WorldSystem.novel_id == novel_id)
    query = apply_ilike_search(query, q, WorldSystem.name, WorldSystem.description)
    visibility = parse_visibility_filter(visibility)
    query = apply_exact_filters(
        query,
        (WorldSystem.origin, origin),
        (WorldSystem.worldpack_pack_id, worldpack_pack_id),
        (WorldSystem.visibility, visibility),
        (WorldSystem.status, status),
        (WorldSystem.display_type, display_type),
    )
    return query.order_by(WorldSystem.id.asc()).all()


@router.post("/systems", response_model=WorldSystemResponse, status_code=201)
def create_system(
    novel_id: int,
    body: WorldSystemCreate,
    db: Session = Depends(get_db),
):
    return run_world_operation(
        crud.create_system,
        novel_id,
        body.model_dump(),
        db=db,
    )


@router.get("/systems/{system_id}", response_model=WorldSystemResponse)
def get_system_route(
    novel_id: int,
    system_id: int,
    db: Session = Depends(get_db),
):
    get_novel(novel_id, db)
    return load_world_system(novel_id, system_id, db)


@router.put("/systems/{system_id}", response_model=WorldSystemResponse)
def update_system(
    novel_id: int,
    system_id: int,
    body: WorldSystemUpdate,
    db: Session = Depends(get_db),
):
    return run_world_operation(
        crud.update_system,
        novel_id,
        system_id,
        body.model_dump(exclude_none=True),
        db=db,
    )


@router.delete("/systems/{system_id}")
def delete_system(
    novel_id: int,
    system_id: int,
    db: Session = Depends(get_db),
):
    run_world_operation(crud.delete_system, novel_id, system_id, db=db)
    return {"message": "System deleted"}


@router.post("/systems/confirm", response_model=BatchConfirmResponse)
def batch_confirm_systems(
    novel_id: int,
    body: BatchConfirmRequest,
    db: Session = Depends(get_db),
):
    count = run_world_operation(
        crud.batch_confirm_systems,
        novel_id,
        body.ids,
        db=db,
    )
    return BatchConfirmResponse(confirmed=count)


@router.post("/systems/reject", response_model=BatchRejectResponse)
def batch_reject_systems(
    novel_id: int,
    body: BatchRejectRequest,
    db: Session = Depends(get_db),
):
    count = run_world_operation(
        crud.batch_reject_systems,
        novel_id,
        body.ids,
        db=db,
    )
    return BatchRejectResponse(rejected=count)


get_system = get_system_route


__all__ = [
    "batch_confirm_systems",
    "batch_reject_systems",
    "create_system",
    "delete_system",
    "get_system",
    "list_systems",
    "router",
    "update_system",
]
