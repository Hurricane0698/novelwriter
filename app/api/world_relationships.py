# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.world import crud
from app.database import get_db
from app.models import WorldRelationship
from app.schemas import (
    BatchConfirmRequest,
    BatchConfirmResponse,
    BatchRejectRequest,
    BatchRejectResponse,
    WorldOrigin,
    WorldRelationshipCreate,
    WorldRelationshipResponse,
    WorldRelationshipUpdate,
)
from app.api.world_support import (
    WorldModelRowStatus,
    apply_exact_filters,
    apply_ilike_search,
    get_entity,
    get_novel,
    parse_visibility_filter,
    run_world_operation,
)

router = APIRouter()


@router.get("/relationships", response_model=List[WorldRelationshipResponse])
def list_relationships(
    novel_id: int,
    q: Optional[str] = None,
    entity_id: Optional[int] = None,
    source_id: Optional[int] = None,
    target_id: Optional[int] = None,
    origin: Optional[WorldOrigin] = None,
    worldpack_pack_id: Optional[str] = None,
    visibility: Optional[str] = None,
    status: Optional[WorldModelRowStatus] = None,
    db: Session = Depends(get_db),
):
    get_novel(novel_id, db)
    query = db.query(WorldRelationship).filter(WorldRelationship.novel_id == novel_id)
    query = apply_ilike_search(query, q, WorldRelationship.label, WorldRelationship.description)
    if entity_id is not None:
        get_entity(novel_id, entity_id, db)
        query = query.filter(
            or_(
                WorldRelationship.source_id == entity_id,
                WorldRelationship.target_id == entity_id,
            )
        )
    if source_id is not None:
        get_entity(novel_id, source_id, db)
        query = query.filter(WorldRelationship.source_id == source_id)
    if target_id is not None:
        get_entity(novel_id, target_id, db)
        query = query.filter(WorldRelationship.target_id == target_id)
    visibility = parse_visibility_filter(visibility)
    query = apply_exact_filters(
        query,
        (WorldRelationship.origin, origin),
        (WorldRelationship.worldpack_pack_id, worldpack_pack_id),
        (WorldRelationship.visibility, visibility),
        (WorldRelationship.status, status),
    )
    return query.order_by(WorldRelationship.id.asc()).all()


@router.post("/relationships", response_model=WorldRelationshipResponse, status_code=201)
def create_relationship(
    novel_id: int,
    body: WorldRelationshipCreate,
    db: Session = Depends(get_db),
):
    return run_world_operation(
        crud.create_relationship,
        novel_id,
        body.model_dump(),
        db=db,
    )


@router.put("/relationships/{relationship_id}", response_model=WorldRelationshipResponse)
def update_relationship(
    novel_id: int,
    relationship_id: int,
    body: WorldRelationshipUpdate,
    db: Session = Depends(get_db),
):
    return run_world_operation(
        crud.update_relationship,
        novel_id,
        relationship_id,
        body.model_dump(exclude_none=True),
        db=db,
    )


@router.delete("/relationships/{relationship_id}")
def delete_relationship(
    novel_id: int,
    relationship_id: int,
    db: Session = Depends(get_db),
):
    run_world_operation(crud.delete_relationship, novel_id, relationship_id, db=db)
    return {"message": "Relationship deleted"}


@router.post("/relationships/confirm", response_model=BatchConfirmResponse)
def batch_confirm_relationships(
    novel_id: int,
    body: BatchConfirmRequest,
    db: Session = Depends(get_db),
):
    count = run_world_operation(
        crud.batch_confirm_relationships,
        novel_id,
        body.ids,
        db=db,
    )
    return BatchConfirmResponse(confirmed=count)


@router.post("/relationships/reject", response_model=BatchRejectResponse)
def batch_reject_relationships(
    novel_id: int,
    body: BatchRejectRequest,
    db: Session = Depends(get_db),
):
    count = run_world_operation(
        crud.batch_reject_relationships,
        novel_id,
        body.ids,
        db=db,
    )
    return BatchRejectResponse(rejected=count)


__all__ = [
    "batch_confirm_relationships",
    "batch_reject_relationships",
    "create_relationship",
    "delete_relationship",
    "list_relationships",
    "router",
    "update_relationship",
]
