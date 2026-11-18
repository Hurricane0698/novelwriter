# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.world import crud
from app.database import get_db
from app.models import WorldEntity
from app.schemas import (
    AttributeReorderRequest,
    BatchConfirmRequest,
    BatchConfirmResponse,
    BatchRejectRequest,
    BatchRejectResponse,
    WorldAttributeCreate,
    WorldAttributeUpdate,
    WorldEntityAttributeResponse,
    WorldEntityCreate,
    WorldEntityDetailResponse,
    WorldEntityResponse,
    WorldEntityUpdate,
    WorldOrigin,
)
from app.api.world_support import (
    WorldModelRowStatus,
    apply_exact_filters,
    apply_ilike_search,
    get_entity as load_world_entity,
    get_novel,
    run_world_operation,
)

router = APIRouter()


@router.get("/entities", response_model=List[WorldEntityResponse])
def list_entities(
    novel_id: int,
    q: Optional[str] = None,
    entity_type: Optional[str] = None,
    origin: Optional[WorldOrigin] = None,
    worldpack_pack_id: Optional[str] = None,
    worldpack_key: Optional[str] = None,
    status: Optional[WorldModelRowStatus] = None,
    db: Session = Depends(get_db),
):
    get_novel(novel_id, db)
    query = db.query(WorldEntity).filter(WorldEntity.novel_id == novel_id)
    query = apply_ilike_search(query, q, WorldEntity.name, WorldEntity.description)
    query = apply_exact_filters(
        query,
        (WorldEntity.entity_type, entity_type),
        (WorldEntity.origin, origin),
        (WorldEntity.worldpack_pack_id, worldpack_pack_id),
        (WorldEntity.worldpack_key, worldpack_key),
        (WorldEntity.status, status),
    )
    return query.order_by(WorldEntity.id.asc()).all()


@router.post("/entities", response_model=WorldEntityResponse, status_code=201)
def create_entity(
    novel_id: int,
    body: WorldEntityCreate,
    db: Session = Depends(get_db),
):
    return run_world_operation(
        crud.create_entity,
        novel_id,
        body.model_dump(),
        db=db,
    )


@router.get("/entities/{entity_id}", response_model=WorldEntityDetailResponse)
def get_entity_route(
    novel_id: int,
    entity_id: int,
    db: Session = Depends(get_db),
):
    get_novel(novel_id, db)
    return load_world_entity(novel_id, entity_id, db)


@router.put("/entities/{entity_id}", response_model=WorldEntityResponse)
def update_entity(
    novel_id: int,
    entity_id: int,
    body: WorldEntityUpdate,
    db: Session = Depends(get_db),
):
    return run_world_operation(
        crud.update_entity,
        novel_id,
        entity_id,
        body.model_dump(exclude_none=True),
        db=db,
    )


@router.delete("/entities/{entity_id}")
def delete_entity(
    novel_id: int,
    entity_id: int,
    db: Session = Depends(get_db),
):
    run_world_operation(crud.delete_entity, novel_id, entity_id, db=db)
    return {"message": "Entity deleted"}


@router.post("/entities/confirm", response_model=BatchConfirmResponse)
def batch_confirm_entities(
    novel_id: int,
    body: BatchConfirmRequest,
    db: Session = Depends(get_db),
):
    count = run_world_operation(
        crud.batch_confirm_entities,
        novel_id,
        body.ids,
        db=db,
    )
    return BatchConfirmResponse(confirmed=count)


@router.post("/entities/reject", response_model=BatchRejectResponse)
def batch_reject_entities(
    novel_id: int,
    body: BatchRejectRequest,
    db: Session = Depends(get_db),
):
    count = run_world_operation(
        crud.batch_reject_entities,
        novel_id,
        body.ids,
        db=db,
    )
    return BatchRejectResponse(rejected=count)


@router.post("/entities/{entity_id}/attributes", response_model=WorldEntityAttributeResponse, status_code=201)
def add_attribute(
    novel_id: int,
    entity_id: int,
    body: WorldAttributeCreate,
    db: Session = Depends(get_db),
):
    return run_world_operation(crud.create_attribute, novel_id, entity_id, body.model_dump(), db=db)


@router.put("/entities/{entity_id}/attributes/{attribute_id}", response_model=WorldEntityAttributeResponse)
def update_attribute(
    novel_id: int,
    entity_id: int,
    attribute_id: int,
    body: WorldAttributeUpdate,
    db: Session = Depends(get_db),
):
    return run_world_operation(
        crud.update_attribute,
        novel_id,
        entity_id,
        attribute_id,
        body.model_dump(exclude_none=True),
        db=db,
    )


@router.delete("/entities/{entity_id}/attributes/{attribute_id}")
def delete_attribute(
    novel_id: int,
    entity_id: int,
    attribute_id: int,
    db: Session = Depends(get_db),
):
    run_world_operation(crud.delete_attribute, novel_id, entity_id, attribute_id, db=db)
    return {"message": "Attribute deleted"}


@router.patch("/entities/{entity_id}/attributes/reorder")
def reorder_attributes(
    novel_id: int,
    entity_id: int,
    body: AttributeReorderRequest,
    db: Session = Depends(get_db),
):
    run_world_operation(crud.reorder_attributes, novel_id, entity_id, body.order, db=db)
    return {"message": "Reordered"}


get_entity = get_entity_route


__all__ = [
    "add_attribute",
    "batch_confirm_entities",
    "batch_reject_entities",
    "create_entity",
    "delete_attribute",
    "delete_entity",
    "get_entity",
    "list_entities",
    "reorder_attributes",
    "router",
    "update_attribute",
    "update_entity",
]
