# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from typing import List, Literal, Optional

from app.config import get_settings
from app.core.ai_client import LLMUnavailableError, StructuredOutputParseError
from app.core.bootstrap import (
    BOOTSTRAP_MODE_INDEX_REFRESH,
    BOOTSTRAP_MODE_INITIAL,
    BOOTSTRAP_MODE_REEXTRACT,
    find_legacy_manual_draft_ambiguity,
    is_running_status,
    is_stale_running_job,
    resolve_bootstrap_mode,
    resolve_reextract_draft_policy,
    run_bootstrap_job,
)
from app.core.auth import (
    get_current_user_or_default,
    check_generation_quota,
    decrement_quota,
    reserve_quota,
    refund_quota,
)
from app.core.events import record_event
from app.core.llm_semaphore import acquire_llm_slot, release_llm_slot
from app.core.world_gen import generate_world_drafts
from app.database import get_db
from app.models import (
    BootstrapJob,
    Chapter,
    Novel,
    User,
    WorldEntity,
    WorldEntityAttribute,
    WorldRelationship,
    WorldSystem,
)
from app.api.deps import verify_novel_access
from app.api.novels import get_llm_config
from app.schemas import (
    AttributeReorderRequest,
    BatchConfirmRequest,
    BatchConfirmResponse,
    BatchRejectRequest,
    BatchRejectResponse,
    BootstrapDraftPolicy,
    BootstrapJobResponse,
    BootstrapMode,
    BootstrapProgress,
    BootstrapResult,
    BootstrapTriggerRequest,
    WorldAttributeCreate,
    WorldAttributeUpdate,
    WorldEntityAttributeResponse,
    WorldEntityCreate,
    WorldEntityDetailResponse,
    WorldEntityResponse,
    WorldEntityUpdate,
    WorldRelationshipCreate,
    WorldRelationshipResponse,
    WorldRelationshipUpdate,
    WorldSystemCreate,
    WorldSystemResponse,
    WorldSystemUpdate,
    WorldpackImportCounts,
    WorldpackImportResponse,
    WorldpackImportWarning,
    WorldpackV1Payload,
    WorldGenerateRequest,
    WorldGenerateResponse,
    WorldOrigin,
    SystemDisplayType,
    _normalize_and_validate_system_data,
)
from app.world_relationships import canonicalize_relationship_label
from app.world_visibility import ALLOWED_VISIBILITIES, normalize_visibility

router = APIRouter(
    prefix="/api/novels/{novel_id}/world",
    tags=["world"],
    dependencies=[Depends(verify_novel_access)],
)
logger = logging.getLogger(__name__)
_bootstrap_trigger_locks: dict[int, asyncio.Lock] = {}
_bootstrap_trigger_locks_guard = asyncio.Lock()
_world_generate_locks: dict[int, asyncio.Lock] = {}
_world_generate_locks_guard = asyncio.Lock()
_LEGACY_REPAIR_SCRIPT = "scripts/fix_legacy_bootstrap_origin.py"
_WORLDPACK_SCHEMA_VERSION = "worldpack.v1"

WorldModelRowStatus = Literal["draft", "confirmed"]


def _error_detail(code: str, message: str) -> dict[str, str]:
    # Frontend maps `code` to user-facing copy; `message` is for diagnostics only.
    return {"code": code, "message": message}


def _parse_visibility_filter(visibility: str | None) -> str | None:
    if visibility is None:
        return None
    normalized = normalize_visibility(visibility)
    if not isinstance(normalized, str):
        raise HTTPException(status_code=422, detail=_error_detail("invalid_visibility", "Invalid visibility"))
    if normalized not in ALLOWED_VISIBILITIES:
        raise HTTPException(status_code=422, detail=_error_detail("invalid_visibility", "Invalid visibility"))
    return normalized


async def _get_bootstrap_trigger_lock(novel_id: int) -> asyncio.Lock:
    async with _bootstrap_trigger_locks_guard:
        lock = _bootstrap_trigger_locks.get(novel_id)
        if lock is None:
            lock = asyncio.Lock()
            _bootstrap_trigger_locks[novel_id] = lock
        return lock


async def _get_world_generate_lock(novel_id: int) -> asyncio.Lock:
    async with _world_generate_locks_guard:
        lock = _world_generate_locks.get(novel_id)
        if lock is None:
            lock = asyncio.Lock()
            _world_generate_locks[novel_id] = lock
        return lock


def _get_novel(novel_id: int, db: Session) -> Novel:
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if not novel:
        raise HTTPException(status_code=404, detail=_error_detail("novel_not_found", "Novel not found"))
    return novel


def _get_entity(novel_id: int, entity_id: int, db: Session) -> WorldEntity:
    entity = db.query(WorldEntity).filter(WorldEntity.id == entity_id, WorldEntity.novel_id == novel_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail=_error_detail("entity_not_found", "Entity not found"))
    return entity


def _has_non_empty_chapter_text(novel_id: int, db: Session) -> bool:
    chapters = db.query(Chapter.content).filter(Chapter.novel_id == novel_id).all()
    return any((content or "").strip() for (content,) in chapters)


def _is_bootstrap_initialized(job: BootstrapJob | None) -> bool:
    if job is None:
        return False

    if bool(getattr(job, "initialized", False)):
        return True

    result = job.result or {}
    if bool(result.get("initialized", False)):
        return True

    if str(job.status) != "completed":
        return False

    if "index_refresh_only" in result:
        return not bool(result.get("index_refresh_only"))

    # Legacy completed jobs predate index-refresh-only mode and imply initialized extraction.
    return True


def _resolve_trigger_params(
    body: BootstrapTriggerRequest | None,
    *,
    bootstrap_initialized: bool,
) -> tuple[str, BootstrapDraftPolicy | None]:
    request = body or BootstrapTriggerRequest()
    mode_explicit = body is not None and "mode" in body.model_fields_set
    mode = request.mode.value
    if not mode_explicit:
        mode = BOOTSTRAP_MODE_INDEX_REFRESH if bootstrap_initialized else BOOTSTRAP_MODE_INITIAL

    if mode != BOOTSTRAP_MODE_REEXTRACT and request.draft_policy is not None:
        raise HTTPException(
            status_code=400,
            detail=_error_detail(
                "bootstrap_draft_policy_not_allowed",
                "draft_policy is only supported for reextract mode",
            ),
        )

    if mode != BOOTSTRAP_MODE_REEXTRACT:
        return mode, None

    raw_policy = request.draft_policy.value if request.draft_policy else None
    policy = BootstrapDraftPolicy(resolve_reextract_draft_policy(raw_policy))
    if (
        policy == BootstrapDraftPolicy.REPLACE_BOOTSTRAP_DRAFTS
        and not request.force
    ):
        raise HTTPException(
            status_code=400,
            detail=_error_detail(
                "bootstrap_force_required",
                "force=true is required for reextract with replace_bootstrap_drafts",
            ),
        )
    return mode, policy


def _mark_entity_origin_manual_if_bootstrap_draft(entity: WorldEntity) -> None:
    if entity.status == "draft" and entity.origin in {"bootstrap", "worldgen"}:
        entity.origin = "manual"


def _mark_entity_origin_manual_if_worldpack(entity: WorldEntity) -> None:
    if entity.origin == "worldpack":
        entity.origin = "manual"


def _mark_relationship_origin_manual_if_bootstrap_draft(relationship: WorldRelationship) -> None:
    if relationship.status == "draft" and relationship.origin in {"bootstrap", "worldgen"}:
        relationship.origin = "manual"


def _mark_relationship_origin_manual_if_worldpack(relationship: WorldRelationship) -> None:
    if relationship.origin == "worldpack":
        relationship.origin = "manual"


def _mark_attribute_origin_manual_if_worldpack(attribute: WorldEntityAttribute) -> None:
    if attribute.origin == "worldpack":
        attribute.origin = "manual"


def _mark_system_origin_manual_if_worldpack(system: WorldSystem) -> None:
    if system.origin == "worldpack":
        system.origin = "manual"


def _mark_system_origin_manual_if_ai_draft(system: WorldSystem) -> None:
    if system.status == "draft" and system.origin in {"bootstrap", "worldgen"}:
        system.origin = "manual"


def _raise_legacy_ambiguity_conflict(novel_id: int, entity_count: int, relationship_count: int) -> None:
    raise HTTPException(
        status_code=409,
        detail=_error_detail(
            "bootstrap_legacy_ambiguity_conflict",
            (
                "Legacy ambiguity detected for reextract replacement: "
                f"{entity_count} draft entities and {relationship_count} draft relationships "
                "still use origin=manual from pre-origin-tracking data. "
                f"Run `python3 {_LEGACY_REPAIR_SCRIPT} --novel-id {novel_id} --dry-run`, "
                "review the output, then rerun with `--apply` before retrying."
            ),
        ),
    )


def _serialize_bootstrap_job(job: BootstrapJob) -> BootstrapJobResponse:
    progress = job.progress or {}
    result = job.result or {}
    mode = BootstrapMode(resolve_bootstrap_mode(getattr(job, "mode", None)))
    return BootstrapJobResponse(
        job_id=job.id,
        novel_id=job.novel_id,
        mode=mode,
        initialized=_is_bootstrap_initialized(job),
        status=job.status,
        progress=BootstrapProgress(
            step=int(progress.get("step", 0)),
            detail=str(progress.get("detail", "")),
        ),
        result=BootstrapResult(
            entities_found=int(result.get("entities_found", 0)),
            relationships_found=int(result.get("relationships_found", 0)),
            index_refresh_only=bool(result.get("index_refresh_only", False)),
        ),
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


# ===========================================================================
# Entities
# ===========================================================================


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
    current_user: User = Depends(get_current_user_or_default),
):
    _get_novel(novel_id, db)
    query = db.query(WorldEntity).filter(WorldEntity.novel_id == novel_id)
    if q:
        needle = q.strip()
        if needle:
            like = f"%{needle}%"
            query = query.filter(or_(WorldEntity.name.ilike(like), WorldEntity.description.ilike(like)))
    if entity_type:
        query = query.filter(WorldEntity.entity_type == entity_type)
    if origin:
        query = query.filter(WorldEntity.origin == origin)
    if worldpack_pack_id:
        query = query.filter(WorldEntity.worldpack_pack_id == worldpack_pack_id)
    if worldpack_key:
        query = query.filter(WorldEntity.worldpack_key == worldpack_key)
    if status:
        query = query.filter(WorldEntity.status == status)
    return query.order_by(WorldEntity.id.asc()).all()


@router.post("/entities", response_model=WorldEntityResponse, status_code=201)
def create_entity(
    novel_id: int,
    body: WorldEntityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _get_novel(novel_id, db)
    entity = WorldEntity(novel_id=novel_id, **body.model_dump())
    db.add(entity)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=_error_detail("entity_name_conflict", "Entity with this name already exists in this novel"),
        )
    db.refresh(entity)
    record_event(db, current_user.id, "world_edit", novel_id=novel_id, meta={"action": "create_entity"})
    return entity


@router.get("/entities/{entity_id}", response_model=WorldEntityDetailResponse)
def get_entity(
    novel_id: int,
    entity_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _get_novel(novel_id, db)
    entity = db.query(WorldEntity).filter(WorldEntity.id == entity_id, WorldEntity.novel_id == novel_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail=_error_detail("entity_not_found", "Entity not found"))
    return entity


@router.put("/entities/{entity_id}", response_model=WorldEntityResponse)
def update_entity(
    novel_id: int,
    entity_id: int,
    body: WorldEntityUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _get_novel(novel_id, db)
    entity = db.query(WorldEntity).filter(WorldEntity.id == entity_id, WorldEntity.novel_id == novel_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail=_error_detail("entity_not_found", "Entity not found"))
    update_data = body.model_dump(exclude_none=True)
    for k, v in update_data.items():
        setattr(entity, k, v)
    if update_data:
        _mark_entity_origin_manual_if_worldpack(entity)
        _mark_entity_origin_manual_if_bootstrap_draft(entity)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=_error_detail("entity_name_conflict", "Entity name conflict"))
    db.refresh(entity)
    record_event(db, current_user.id, "world_edit", novel_id=novel_id, meta={"action": "update_entity"})
    return entity


@router.delete("/entities/{entity_id}")
def delete_entity(
    novel_id: int,
    entity_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _get_novel(novel_id, db)
    entity = db.query(WorldEntity).filter(WorldEntity.id == entity_id, WorldEntity.novel_id == novel_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail=_error_detail("entity_not_found", "Entity not found"))
    db.delete(entity)
    db.commit()
    return {"message": "Entity deleted"}


@router.post("/entities/confirm", response_model=BatchConfirmResponse)
def batch_confirm_entities(
    novel_id: int,
    body: BatchConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _get_novel(novel_id, db)
    count = db.query(WorldEntity).filter(
        WorldEntity.novel_id == novel_id,
        WorldEntity.id.in_(body.ids),
        WorldEntity.status == "draft",
    ).update({"status": "confirmed"}, synchronize_session="fetch")
    db.commit()
    record_event(db, current_user.id, "draft_confirm", novel_id=novel_id, meta={"type": "entity", "count": count})
    return BatchConfirmResponse(confirmed=count)


@router.post("/entities/reject", response_model=BatchRejectResponse)
def batch_reject_entities(
    novel_id: int,
    body: BatchRejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _get_novel(novel_id, db)
    entities = (
        db.query(WorldEntity)
        .filter(
            WorldEntity.novel_id == novel_id,
            WorldEntity.id.in_(body.ids),
            WorldEntity.status == "draft",
        )
        .all()
    )
    for entity in entities:
        db.delete(entity)
    db.commit()
    record_event(db, current_user.id, "draft_reject", novel_id=novel_id, meta={"type": "entity", "count": len(entities)})
    return BatchRejectResponse(rejected=len(entities))


# ===========================================================================
# Attributes
# ===========================================================================


@router.post("/entities/{entity_id}/attributes", response_model=WorldEntityAttributeResponse, status_code=201)
def add_attribute(
    novel_id: int,
    entity_id: int,
    body: WorldAttributeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _get_novel(novel_id, db)
    entity = db.query(WorldEntity).filter(WorldEntity.id == entity_id, WorldEntity.novel_id == novel_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail=_error_detail("entity_not_found", "Entity not found"))
    _mark_entity_origin_manual_if_bootstrap_draft(entity)
    attr = WorldEntityAttribute(entity_id=entity_id, **body.model_dump())
    db.add(attr)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=_error_detail(
                "attribute_key_conflict",
                "Attribute with this key already exists for this entity",
            ),
        )
    db.refresh(attr)
    return attr


@router.put("/entities/{entity_id}/attributes/{attribute_id}", response_model=WorldEntityAttributeResponse)
def update_attribute(
    novel_id: int,
    entity_id: int,
    attribute_id: int,
    body: WorldAttributeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    entity = _get_entity(novel_id, entity_id, db)
    attr = db.query(WorldEntityAttribute).filter(
        WorldEntityAttribute.id == attribute_id,
        WorldEntityAttribute.entity_id == entity_id,
    ).first()
    if not attr:
        raise HTTPException(status_code=404, detail=_error_detail("attribute_not_found", "Attribute not found"))
    update_data = body.model_dump(exclude_none=True)
    for k, v in update_data.items():
        setattr(attr, k, v)
    if update_data:
        _mark_attribute_origin_manual_if_worldpack(attr)
        _mark_entity_origin_manual_if_bootstrap_draft(entity)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=_error_detail("attribute_key_conflict", "Attribute key conflict"),
        )
    db.refresh(attr)
    return attr


@router.delete("/entities/{entity_id}/attributes/{attribute_id}")
def delete_attribute(
    novel_id: int,
    entity_id: int,
    attribute_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    entity = _get_entity(novel_id, entity_id, db)
    attr = db.query(WorldEntityAttribute).filter(
        WorldEntityAttribute.id == attribute_id,
        WorldEntityAttribute.entity_id == entity_id,
    ).first()
    if not attr:
        raise HTTPException(status_code=404, detail=_error_detail("attribute_not_found", "Attribute not found"))
    _mark_entity_origin_manual_if_bootstrap_draft(entity)
    db.delete(attr)
    db.commit()
    return {"message": "Attribute deleted"}


@router.patch("/entities/{entity_id}/attributes/reorder")
def reorder_attributes(
    novel_id: int,
    entity_id: int,
    body: AttributeReorderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    entity = _get_entity(novel_id, entity_id, db)
    _mark_entity_origin_manual_if_bootstrap_draft(entity)
    for i, attr_id in enumerate(body.order):
        db.query(WorldEntityAttribute).filter(
            WorldEntityAttribute.id == attr_id,
            WorldEntityAttribute.entity_id == entity_id,
        ).update({"sort_order": i})
    db.commit()
    return {"message": "Reordered"}


# ===========================================================================
# Relationships
# ===========================================================================


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
    current_user: User = Depends(get_current_user_or_default),
):
    _get_novel(novel_id, db)
    query = db.query(WorldRelationship).filter(WorldRelationship.novel_id == novel_id)
    if q:
        needle = q.strip()
        if needle:
            like = f"%{needle}%"
            query = query.filter(or_(WorldRelationship.label.ilike(like), WorldRelationship.description.ilike(like)))
    if entity_id is not None:
        _get_entity(novel_id, entity_id, db)
        query = query.filter(
            or_(
                WorldRelationship.source_id == entity_id,
                WorldRelationship.target_id == entity_id,
            )
        )
    if source_id is not None:
        _get_entity(novel_id, source_id, db)
        query = query.filter(WorldRelationship.source_id == source_id)
    if target_id is not None:
        _get_entity(novel_id, target_id, db)
        query = query.filter(WorldRelationship.target_id == target_id)
    if origin:
        query = query.filter(WorldRelationship.origin == origin)
    if worldpack_pack_id:
        query = query.filter(WorldRelationship.worldpack_pack_id == worldpack_pack_id)
    visibility = _parse_visibility_filter(visibility)
    if visibility:
        query = query.filter(WorldRelationship.visibility == visibility)
    if status:
        query = query.filter(WorldRelationship.status == status)
    return query.order_by(WorldRelationship.id.asc()).all()


@router.post("/relationships", response_model=WorldRelationshipResponse, status_code=201)
def create_relationship(
    novel_id: int,
    body: WorldRelationshipCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _get_novel(novel_id, db)
    _get_entity(novel_id, body.source_id, db)
    _get_entity(novel_id, body.target_id, db)
    label_canonical = canonicalize_relationship_label(body.label)
    existing = (
        db.query(WorldRelationship)
        .filter(
            WorldRelationship.novel_id == novel_id,
            WorldRelationship.source_id == body.source_id,
            WorldRelationship.target_id == body.target_id,
            WorldRelationship.label_canonical == label_canonical,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail=_error_detail("relationship_conflict", "Relationship conflict"))
    rel = WorldRelationship(novel_id=novel_id, **body.model_dump())
    db.add(rel)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=_error_detail("relationship_conflict", "Relationship conflict"))
    db.refresh(rel)
    record_event(db, current_user.id, "world_edit", novel_id=novel_id, meta={"action": "create_relationship"})
    return rel


@router.put("/relationships/{relationship_id}", response_model=WorldRelationshipResponse)
def update_relationship(
    novel_id: int,
    relationship_id: int,
    body: WorldRelationshipUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _get_novel(novel_id, db)
    rel = db.query(WorldRelationship).filter(
        WorldRelationship.id == relationship_id,
        WorldRelationship.novel_id == novel_id,
    ).first()
    if not rel:
        raise HTTPException(
            status_code=404,
            detail=_error_detail("relationship_not_found", "Relationship not found"),
        )
    update_data = body.model_dump(exclude_none=True)
    if "label" in update_data:
        label_canonical = canonicalize_relationship_label(update_data["label"])
        conflict = (
            db.query(WorldRelationship)
            .filter(
                WorldRelationship.novel_id == novel_id,
                WorldRelationship.source_id == rel.source_id,
                WorldRelationship.target_id == rel.target_id,
                WorldRelationship.label_canonical == label_canonical,
                WorldRelationship.id != rel.id,
            )
            .first()
        )
        if conflict:
            raise HTTPException(status_code=409, detail=_error_detail("relationship_conflict", "Relationship conflict"))
    for k, v in update_data.items():
        setattr(rel, k, v)
    if update_data:
        _mark_relationship_origin_manual_if_worldpack(rel)
        _mark_relationship_origin_manual_if_bootstrap_draft(rel)
    db.commit()
    db.refresh(rel)
    record_event(db, current_user.id, "world_edit", novel_id=novel_id, meta={"action": "update_relationship"})
    return rel

@router.delete("/relationships/{relationship_id}")
def delete_relationship(
    novel_id: int,
    relationship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _get_novel(novel_id, db)
    rel = db.query(WorldRelationship).filter(
        WorldRelationship.id == relationship_id,
        WorldRelationship.novel_id == novel_id,
    ).first()
    if not rel:
        raise HTTPException(
            status_code=404,
            detail=_error_detail("relationship_not_found", "Relationship not found"),
        )
    db.delete(rel)
    db.commit()
    return {"message": "Relationship deleted"}


@router.post("/relationships/confirm", response_model=BatchConfirmResponse)
def batch_confirm_relationships(
    novel_id: int,
    body: BatchConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _get_novel(novel_id, db)
    count = db.query(WorldRelationship).filter(
        WorldRelationship.novel_id == novel_id,
        WorldRelationship.id.in_(body.ids),
        WorldRelationship.status == "draft",
    ).update({"status": "confirmed"}, synchronize_session="fetch")
    db.commit()
    record_event(db, current_user.id, "draft_confirm", novel_id=novel_id, meta={"type": "relationship", "count": count})
    return BatchConfirmResponse(confirmed=count)


@router.post("/relationships/reject", response_model=BatchRejectResponse)
def batch_reject_relationships(
    novel_id: int,
    body: BatchRejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _get_novel(novel_id, db)
    count = db.query(WorldRelationship).filter(
        WorldRelationship.novel_id == novel_id,
        WorldRelationship.id.in_(body.ids),
        WorldRelationship.status == "draft",
    ).delete(synchronize_session=False)
    db.commit()
    record_event(db, current_user.id, "draft_reject", novel_id=novel_id, meta={"type": "relationship", "count": count})
    return BatchRejectResponse(rejected=count)


# ===========================================================================
# Systems
# ===========================================================================


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
    current_user: User = Depends(get_current_user_or_default),
):
    _get_novel(novel_id, db)
    query = db.query(WorldSystem).filter(WorldSystem.novel_id == novel_id)
    if q:
        needle = q.strip()
        if needle:
            like = f"%{needle}%"
            query = query.filter(or_(WorldSystem.name.ilike(like), WorldSystem.description.ilike(like)))
    if origin:
        query = query.filter(WorldSystem.origin == origin)
    if worldpack_pack_id:
        query = query.filter(WorldSystem.worldpack_pack_id == worldpack_pack_id)
    visibility = _parse_visibility_filter(visibility)
    if visibility:
        query = query.filter(WorldSystem.visibility == visibility)
    if status:
        query = query.filter(WorldSystem.status == status)
    if display_type:
        query = query.filter(WorldSystem.display_type == display_type)
    return query.order_by(WorldSystem.id.asc()).all()


@router.post("/systems", response_model=WorldSystemResponse, status_code=201)
def create_system(
    novel_id: int,
    body: WorldSystemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _get_novel(novel_id, db)
    system = WorldSystem(novel_id=novel_id, **body.model_dump())
    db.add(system)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=_error_detail(
                "system_name_conflict",
                "System with this name already exists in this novel",
            ),
        )
    db.refresh(system)
    record_event(db, current_user.id, "world_edit", novel_id=novel_id, meta={"action": "create_system"})
    return system


@router.get("/systems/{system_id}", response_model=WorldSystemResponse)
def get_system(
    novel_id: int,
    system_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _get_novel(novel_id, db)
    system = db.query(WorldSystem).filter(WorldSystem.id == system_id, WorldSystem.novel_id == novel_id).first()
    if not system:
        raise HTTPException(status_code=404, detail=_error_detail("system_not_found", "System not found"))
    return system


@router.put("/systems/{system_id}", response_model=WorldSystemResponse)
def update_system(
    novel_id: int,
    system_id: int,
    body: WorldSystemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _get_novel(novel_id, db)
    system = db.query(WorldSystem).filter(WorldSystem.id == system_id, WorldSystem.novel_id == novel_id).first()
    if not system:
        raise HTTPException(status_code=404, detail=_error_detail("system_not_found", "System not found"))
    update_data = body.model_dump(exclude_none=True)
    for k, v in update_data.items():
        setattr(system, k, v)
    if "data" in update_data or "display_type" in update_data:
        try:
            system.data = _normalize_and_validate_system_data(system.display_type, system.data)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors())
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=_error_detail("invalid_system_display_type", str(exc)),
            )
    if update_data:
        _mark_system_origin_manual_if_worldpack(system)
        _mark_system_origin_manual_if_ai_draft(system)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=_error_detail("system_name_conflict", "System name conflict"))
    db.refresh(system)
    record_event(db, current_user.id, "world_edit", novel_id=novel_id, meta={"action": "update_system"})
    return system


@router.delete("/systems/{system_id}")
def delete_system(
    novel_id: int,
    system_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _get_novel(novel_id, db)
    system = db.query(WorldSystem).filter(WorldSystem.id == system_id, WorldSystem.novel_id == novel_id).first()
    if not system:
        raise HTTPException(status_code=404, detail=_error_detail("system_not_found", "System not found"))
    db.delete(system)
    db.commit()
    return {"message": "System deleted"}


@router.post("/systems/confirm", response_model=BatchConfirmResponse)
def batch_confirm_systems(
    novel_id: int,
    body: BatchConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _get_novel(novel_id, db)
    count = db.query(WorldSystem).filter(
        WorldSystem.novel_id == novel_id,
        WorldSystem.id.in_(body.ids),
        WorldSystem.status == "draft",
    ).update({"status": "confirmed"}, synchronize_session="fetch")
    db.commit()
    record_event(db, current_user.id, "draft_confirm", novel_id=novel_id, meta={"type": "system", "count": count})
    return BatchConfirmResponse(confirmed=count)


@router.post("/systems/reject", response_model=BatchRejectResponse)
def batch_reject_systems(
    novel_id: int,
    body: BatchRejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _get_novel(novel_id, db)
    count = db.query(WorldSystem).filter(
        WorldSystem.novel_id == novel_id,
        WorldSystem.id.in_(body.ids),
        WorldSystem.status == "draft",
    ).delete(synchronize_session=False)
    db.commit()
    record_event(db, current_user.id, "draft_reject", novel_id=novel_id, meta={"type": "system", "count": count})
    return BatchRejectResponse(rejected=count)


# ===========================================================================
# Worldpack Import
# ===========================================================================

@router.post("/worldpack/import", response_model=WorldpackImportResponse)
def import_worldpack_v1(
    novel_id: int,
    body: WorldpackV1Payload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _get_novel(novel_id, db)
    if body.schema_version != _WORLDPACK_SCHEMA_VERSION:
        raise HTTPException(
            status_code=400,
            detail=_error_detail("worldpack_unsupported_schema_version", "Unsupported schema_version"),
        )

    pack_id = body.pack_id
    counts = WorldpackImportCounts()
    warnings: list[WorldpackImportWarning] = []

    def _warn(code: str, message: str, *, path: str | None = None) -> None:
        warnings.append(WorldpackImportWarning(code=code, message=message, path=path))

    # Preserved/promoted rows (origin!=worldpack) are intentionally not overwritten. We surface
    # these as warnings so users can understand why an import "did nothing" for specific items.
    preserved_entity_keys: set[str] = set()
    preserved_attr_keys_by_entity: dict[str, set[str]] = {}
    preserved_relationship_sigs: set[str] = set()
    preserved_system_names: set[str] = set()

    def _format_sample(items: list[str], *, max_items: int = 6) -> str:
        sample = items[:max_items]
        rest = len(items) - len(sample)
        if rest > 0:
            return f"{', '.join(sample)} (+{rest} more)"
        return ", ".join(sample)

    # Warn on ambiguous alias across entities in the incoming payload.
    alias_to_keys: dict[str, set[str]] = {}
    for entity in body.entities:
        for raw_alias in entity.aliases or []:
            alias = (raw_alias or "").strip()
            if not alias:
                continue
            alias_to_keys.setdefault(alias, set()).add(entity.key)
    for alias, keys in sorted(alias_to_keys.items()):
        if len(keys) > 1:
            _warn(
                "ambiguous_alias",
                f"Alias '{alias}' maps to multiple entities: {sorted(keys)}",
                path="entities[*].aliases",
            )

    # -----------------------------------------------------------------------
    # Entities + Attributes
    # -----------------------------------------------------------------------
    seen_entity_keys: set[str] = set()
    entities_by_key: dict[str, WorldEntity] = {}
    desired_entity_keys: set[str] = set()

    for idx, entity_in in enumerate(body.entities):
        if entity_in.key in seen_entity_keys:
            _warn(
                "duplicate_entity_key",
                f"Duplicate entity key '{entity_in.key}' in payload; skipped",
                path=f"entities[{idx}].key",
            )
            continue
        seen_entity_keys.add(entity_in.key)

        name = (entity_in.name or "").strip()
        if not name:
            # If the entity already exists in DB (from a prior import), keep it for
            # relationship resolution and to avoid partial-sync deletions.
            existing = (
                db.query(WorldEntity)
                .filter(
                    WorldEntity.novel_id == novel_id,
                    WorldEntity.worldpack_pack_id == pack_id,
                    WorldEntity.worldpack_key == entity_in.key,
                )
                .first()
            )
            if existing is None:
                _warn(
                    "missing_name",
                    f"Entity '{entity_in.key}' missing name; skipped",
                    path=f"entities[{idx}].name",
                )
                continue

            desired_entity_keys.add(entity_in.key)
            entities_by_key[entity_in.key] = existing
            _warn(
                "missing_name_preserve_existing",
                f"Entity '{entity_in.key}' missing name; kept existing row for relationship resolution",
                path=f"entities[{idx}].name",
            )
            continue

        desired_entity_keys.add(entity_in.key)

        entity = (
            db.query(WorldEntity)
            .filter(
                WorldEntity.novel_id == novel_id,
                WorldEntity.worldpack_pack_id == pack_id,
                WorldEntity.worldpack_key == entity_in.key,
            )
            .first()
        )
        if entity is None:
            # Avoid unique (novel_id, name) conflicts: if a manual entity already exists
            # with the same name, link it to this pack identity without overwriting.
            by_name = (
                db.query(WorldEntity)
                .filter(WorldEntity.novel_id == novel_id, WorldEntity.name == name)
                .first()
            )
            if by_name is not None:
                if (
                    by_name.worldpack_pack_id
                    and by_name.worldpack_pack_id != pack_id
                    or by_name.worldpack_key
                    and by_name.worldpack_key != entity_in.key
                ):
                    _warn(
                        "entity_name_conflict",
                        f"Entity name '{name}' already exists and is linked to a different worldpack identity; skipped",
                        path=f"entities[{idx}].name",
                    )
                    continue
                # Link the existing row to this pack identity so relationships can resolve.
                linked_changed = False
                if by_name.worldpack_pack_id != pack_id:
                    by_name.worldpack_pack_id = pack_id
                    linked_changed = True
                if by_name.worldpack_key != entity_in.key:
                    by_name.worldpack_key = entity_in.key
                    linked_changed = True
                if linked_changed:
                    counts.entities_updated += 1
                entity = by_name
                _warn(
                    "entity_linked_by_name",
                    f"Entity '{entity_in.key}' linked to existing row by name '{name}'",
                    path=f"entities[{idx}]",
                )
            else:
                entity = WorldEntity(
                    novel_id=novel_id,
                    name=name,
                    entity_type=entity_in.entity_type,
                    description=entity_in.description or "",
                    aliases=entity_in.aliases or [],
                    origin="worldpack",
                    status="confirmed",
                    worldpack_pack_id=pack_id,
                    worldpack_key=entity_in.key,
                )
                db.add(entity)
                db.flush()
                counts.entities_created += 1
        else:
            if entity.origin == "worldpack":
                changed = False
                if entity.name != name:
                    entity.name = name
                    changed = True
                if entity.entity_type != entity_in.entity_type:
                    entity.entity_type = entity_in.entity_type
                    changed = True
                description = entity_in.description or ""
                if entity.description != description:
                    entity.description = description
                    changed = True
                aliases = entity_in.aliases or []
                if entity.aliases != aliases:
                    entity.aliases = aliases
                    changed = True
                if entity.status != "confirmed":
                    entity.status = "confirmed"
                    changed = True
                if changed:
                    counts.entities_updated += 1
            else:
                would_change = (
                    entity.name != name
                    or entity.entity_type != entity_in.entity_type
                    or (entity.description or "") != (entity_in.description or "")
                    or (entity.aliases or []) != (entity_in.aliases or [])
                    or entity.status != "confirmed"
                )
                if would_change:
                    preserved_entity_keys.add(entity_in.key)

        entities_by_key[entity_in.key] = entity

        # Attributes: per-key upsert, overwrite only origin=worldpack.
        desired_attr_keys: set[str] = set()
        for attr_idx, attr_in in enumerate(entity_in.attributes):
            desired_attr_keys.add(attr_in.key)
            attr = (
                db.query(WorldEntityAttribute)
                .filter(
                    WorldEntityAttribute.entity_id == entity.id,
                    WorldEntityAttribute.key == attr_in.key,
                )
                .first()
            )
            if attr is None:
                vis = attr_in.visibility
                attr = WorldEntityAttribute(
                    entity_id=entity.id,
                    key=attr_in.key,
                    surface=attr_in.surface,
                    truth=attr_in.truth,
                    visibility=vis,
                    sort_order=attr_idx,
                    origin="worldpack",
                    worldpack_pack_id=pack_id,
                )
                db.add(attr)
                counts.attributes_created += 1
                continue

            if attr.origin != "worldpack":
                # Preserved/promoted; do not overwrite.
                desired_vis = attr_in.visibility
                would_change = (
                    attr.surface != attr_in.surface
                    or (attr.truth or None) != (attr_in.truth or None)
                    or attr.visibility != desired_vis
                    or attr.sort_order != attr_idx
                )
                if would_change:
                    preserved_attr_keys_by_entity.setdefault(entity_in.key, set()).add(attr_in.key)
                continue

            changed = False
            if attr.surface != attr_in.surface:
                attr.surface = attr_in.surface
                changed = True
            if (attr.truth or None) != (attr_in.truth or None):
                attr.truth = attr_in.truth
                changed = True
            desired_vis = attr_in.visibility
            if attr.visibility != desired_vis:
                attr.visibility = desired_vis
                changed = True
            if attr.sort_order != attr_idx:
                attr.sort_order = attr_idx
                changed = True
            if attr.worldpack_pack_id != pack_id:
                attr.worldpack_pack_id = pack_id
                changed = True
            if changed:
                counts.attributes_updated += 1

        # Delete attributes removed from this pack (origin=worldpack only).
        existing_attrs = (
            db.query(WorldEntityAttribute)
            .filter(
                WorldEntityAttribute.entity_id == entity.id,
                WorldEntityAttribute.origin == "worldpack",
                WorldEntityAttribute.worldpack_pack_id == pack_id,
            )
            .all()
        )
        for attr in existing_attrs:
            if attr.key not in desired_attr_keys:
                db.delete(attr)
                counts.attributes_deleted += 1

    # -----------------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------------
    desired_relationship_sigs: set[tuple[int, int, str]] = set()
    for idx, rel_in in enumerate(body.relationships):
        label = (rel_in.label or "").strip()
        if not label:
            _warn(
                "missing_relationship_label",
                "Relationship missing label; skipped",
                path=f"relationships[{idx}].label",
            )
            continue
        label_canonical = canonicalize_relationship_label(label)
        source = entities_by_key.get(rel_in.source_key)
        target = entities_by_key.get(rel_in.target_key)
        if source is None or target is None:
            _warn(
                "missing_relationship_refs",
                f"Relationship refs missing: source_key='{rel_in.source_key}', target_key='{rel_in.target_key}'",
                path=f"relationships[{idx}]",
            )
            continue
        sig = (source.id, target.id, label_canonical)
        desired_relationship_sigs.add(sig)

        rel = (
            db.query(WorldRelationship)
            .filter(
                WorldRelationship.novel_id == novel_id,
                WorldRelationship.source_id == source.id,
                WorldRelationship.target_id == target.id,
                WorldRelationship.label_canonical == label_canonical,
            )
            .first()
        )
        if rel is None:
            vis = rel_in.visibility
            rel = WorldRelationship(
                novel_id=novel_id,
                source_id=source.id,
                target_id=target.id,
                label=label,
                description=rel_in.description or "",
                visibility=vis,
                origin="worldpack",
                status="confirmed",
                worldpack_pack_id=pack_id,
            )
            db.add(rel)
            counts.relationships_created += 1
            continue

        if rel.origin != "worldpack" or rel.worldpack_pack_id != pack_id:
            # Preserved/promoted; do not overwrite.
            desired_vis = rel_in.visibility
            incoming_desc = rel_in.description or ""
            would_change = (
                rel.label != label
                or (rel.description or "") != incoming_desc
                or rel.visibility != desired_vis
                or rel.status != "confirmed"
            )
            if would_change:
                preserved_relationship_sigs.add(f"{rel_in.source_key} --{label}--> {rel_in.target_key}")
            continue

        changed = False
        description = rel_in.description or ""
        if rel.label != label:
            rel.label = label
            changed = True
        if rel.description != description:
            rel.description = description
            changed = True
        desired_vis = rel_in.visibility
        if rel.visibility != desired_vis:
            rel.visibility = desired_vis
            changed = True
        if rel.status != "confirmed":
            rel.status = "confirmed"
            changed = True
        if rel.worldpack_pack_id != pack_id:
            rel.worldpack_pack_id = pack_id
            changed = True
        if changed:
            counts.relationships_updated += 1

    # Delete relationships removed from this pack (origin=worldpack only).
    existing_rels = (
        db.query(WorldRelationship)
        .filter(
            WorldRelationship.novel_id == novel_id,
            WorldRelationship.origin == "worldpack",
            WorldRelationship.worldpack_pack_id == pack_id,
        )
        .all()
    )
    for rel in existing_rels:
        sig_label = rel.label_canonical or canonicalize_relationship_label(rel.label)
        sig = (rel.source_id, rel.target_id, sig_label)
        if sig not in desired_relationship_sigs:
            db.delete(rel)
            counts.relationships_deleted += 1

    # -----------------------------------------------------------------------
    # Systems
    # -----------------------------------------------------------------------
    desired_system_names: set[str] = set()
    for idx, system_in in enumerate(body.systems):
        name = (system_in.name or "").strip()
        if not name:
            _warn(
                "missing_name",
                "System missing name; skipped",
                path=f"systems[{idx}].name",
            )
            continue
        desired_system_names.add(name)

        system = (
            db.query(WorldSystem)
            .filter(WorldSystem.novel_id == novel_id, WorldSystem.name == name)
            .first()
        )
        if system is None:
            vis = system_in.visibility
            system = WorldSystem(
                novel_id=novel_id,
                name=name,
                display_type=system_in.display_type,
                description=system_in.description or "",
                data=system_in.data or {},
                constraints=system_in.constraints or [],
                visibility=vis,
                origin="worldpack",
                status="confirmed",
                worldpack_pack_id=pack_id,
            )
            db.add(system)
            counts.systems_created += 1
            continue

        if system.origin != "worldpack":
            desired_vis = system_in.visibility
            would_change = (
                system.display_type != system_in.display_type
                or (system.description or "") != (system_in.description or "")
                or (system.data or {}) != (system_in.data or {})
                or (system.constraints or []) != (system_in.constraints or [])
                or system.visibility != desired_vis
                or system.status != "confirmed"
            )
            if would_change:
                preserved_system_names.add(name)
            continue
        if system.worldpack_pack_id and system.worldpack_pack_id != pack_id:
            _warn(
                "system_name_conflict",
                f"System name '{name}' already exists for a different pack; skipped",
                path=f"systems[{idx}].name",
            )
            continue

        changed = False
        if system.display_type != system_in.display_type:
            system.display_type = system_in.display_type
            changed = True
        description = system_in.description or ""
        if system.description != description:
            system.description = description
            changed = True
        data = system_in.data or {}
        if system.data != data:
            system.data = data
            changed = True
        constraints = system_in.constraints or []
        if system.constraints != constraints:
            system.constraints = constraints
            changed = True
        desired_vis = system_in.visibility
        if system.visibility != desired_vis:
            system.visibility = desired_vis
            changed = True
        if system.status != "confirmed":
            system.status = "confirmed"
            changed = True
        if system.worldpack_pack_id != pack_id:
            system.worldpack_pack_id = pack_id
            changed = True
        if changed:
            counts.systems_updated += 1

    existing_systems = (
        db.query(WorldSystem)
        .filter(
            WorldSystem.novel_id == novel_id,
            WorldSystem.origin == "worldpack",
            WorldSystem.worldpack_pack_id == pack_id,
        )
        .all()
    )
    for system in existing_systems:
        if system.name not in desired_system_names:
            db.delete(system)
            counts.systems_deleted += 1

    # -----------------------------------------------------------------------
    # Entity deletions (pack removed items)
    # -----------------------------------------------------------------------
    entities_to_delete = (
        db.query(WorldEntity)
        .filter(
            WorldEntity.novel_id == novel_id,
            WorldEntity.origin == "worldpack",
            WorldEntity.worldpack_pack_id == pack_id,
            ~WorldEntity.worldpack_key.in_(sorted(desired_entity_keys)),
        )
        .all()
        if desired_entity_keys
        else db.query(WorldEntity)
        .filter(
            WorldEntity.novel_id == novel_id,
            WorldEntity.origin == "worldpack",
            WorldEntity.worldpack_pack_id == pack_id,
        )
        .all()
    )

    for entity in entities_to_delete:
        # Deleting a worldpack entity would also delete dependent rows; skip if any
        # dependency is not part of this pack's worldpack data.
        has_non_pack_attr = (
            db.query(WorldEntityAttribute.id)
            .filter(WorldEntityAttribute.entity_id == entity.id)
            .filter(
                ~and_(
                    WorldEntityAttribute.origin == "worldpack",
                    WorldEntityAttribute.worldpack_pack_id == pack_id,
                )
            )
            .first()
            is not None
        )
        has_non_pack_rel = (
            db.query(WorldRelationship.id)
            .filter(WorldRelationship.novel_id == novel_id)
            .filter(or_(WorldRelationship.source_id == entity.id, WorldRelationship.target_id == entity.id))
            .filter(
                ~and_(
                    WorldRelationship.origin == "worldpack",
                    WorldRelationship.worldpack_pack_id == pack_id,
                )
            )
            .first()
            is not None
        )
        if has_non_pack_attr or has_non_pack_rel:
            _warn(
                "skip_delete_promoted_entity",
                f"Entity '{entity.worldpack_key}' has non-worldpack dependencies; kept",
                path="entities",
            )
            continue

        # Count and remove attributes explicitly to avoid relying on ORM cascades.
        attrs = (
            db.query(WorldEntityAttribute)
            .filter(
                WorldEntityAttribute.entity_id == entity.id,
                WorldEntityAttribute.origin == "worldpack",
                WorldEntityAttribute.worldpack_pack_id == pack_id,
            )
            .all()
        )
        for attr in attrs:
            db.delete(attr)
            counts.attributes_deleted += 1

        db.delete(entity)
        counts.entities_deleted += 1

    if preserved_entity_keys:
        keys = sorted(preserved_entity_keys)
        _warn(
            "preserved_entities_skipped",
            f"Skipped overwriting {len(keys)} preserved entities: {_format_sample(keys)}",
            path="entities",
        )

    if preserved_attr_keys_by_entity:
        total = sum(len(v) for v in preserved_attr_keys_by_entity.values())
        sample_entities = sorted(preserved_attr_keys_by_entity.keys())[:3]
        parts: list[str] = []
        for entity_key in sample_entities:
            keys = sorted(preserved_attr_keys_by_entity[entity_key])
            parts.append(f"{entity_key}[{_format_sample(keys, max_items=3)}]")
        rest = len(preserved_attr_keys_by_entity) - len(sample_entities)
        suffix = f" (+{rest} more entities)" if rest > 0 else ""
        _warn(
            "preserved_attributes_skipped",
            f"Skipped overwriting {total} preserved attributes: {'; '.join(parts)}{suffix}",
            path="entities[*].attributes",
        )

    if preserved_relationship_sigs:
        sigs = sorted(preserved_relationship_sigs)
        _warn(
            "preserved_relationships_skipped",
            f"Skipped overwriting {len(sigs)} preserved relationships: {_format_sample(sigs)}",
            path="relationships",
        )

    if preserved_system_names:
        names = sorted(preserved_system_names)
        _warn(
            "preserved_systems_skipped",
            f"Skipped overwriting {len(names)} preserved systems: {_format_sample(names)}",
            path="systems",
        )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=_error_detail("worldpack_import_conflict", "Worldpack import conflict"),
        )

    return WorldpackImportResponse(pack_id=pack_id, counts=counts, warnings=warnings)


# ===========================================================================
# World Generation
# ===========================================================================


@router.post("/generate", response_model=WorldGenerateResponse)
async def generate_world_from_text(
    novel_id: int,
    body: WorldGenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
    llm_config: dict | None = Depends(get_llm_config),
    _quota_user: User = Depends(check_generation_quota),
):
    lock = await _get_world_generate_lock(novel_id)
    async with lock:
        _get_novel(novel_id, db)
        extra = {
            "request_id": getattr(getattr(request, "state", None), "request_id", None),
            "novel_id": novel_id,
            "user_id": current_user.id,
        }
        await acquire_llm_slot()
        reserved = False
        try:
            try:
                reserve_quota(db, current_user.id, count=1)
                reserved = True
                result = await generate_world_drafts(
                    db=db,
                    novel_id=novel_id,
                    text=body.text,
                    llm_config=llm_config,
                    user_id=current_user.id,
                )
            except HTTPException:
                if reserved:
                    refund_quota(db, current_user.id, count=1)
                raise
            except StructuredOutputParseError:
                if reserved:
                    refund_quota(db, current_user.id, count=1)
                logger.warning(
                    "world.generate invalid LLM output",
                    exc_info=True,
                    extra=extra,
                )
                raise HTTPException(
                    status_code=502,
                    detail=_error_detail("world_generate_llm_schema_invalid", "LLM schema invalid"),
                )
            except LLMUnavailableError:
                if reserved:
                    refund_quota(db, current_user.id, count=1)
                logger.warning(
                    "world.generate LLM unavailable",
                    exc_info=True,
                    extra=extra,
                )
                raise HTTPException(
                    status_code=503,
                    detail=_error_detail("world_generate_llm_unavailable", "LLM unavailable"),
                )
            except IntegrityError:
                if reserved:
                    refund_quota(db, current_user.id, count=1)
                raise HTTPException(
                    status_code=409,
                    detail=_error_detail("world_generate_conflict", "World generation conflict"),
                )
            except Exception:
                if reserved:
                    refund_quota(db, current_user.id, count=1)
                logger.exception("world.generate failed", extra=extra)
                raise HTTPException(
                    status_code=500,
                    detail=_error_detail("world_generate_failed", "World generation failed"),
                )
        finally:
            release_llm_slot()

        # Hosted quota is pay-per-completion. We reserve quota before generation and
        # refund on failure so retries don't burn quota.
        record_event(db, current_user.id, "world_generate", novel_id=novel_id)
        return result


# ===========================================================================
# Bootstrap
# ===========================================================================


@router.post("/bootstrap", response_model=BootstrapJobResponse, status_code=202)
async def trigger_bootstrap(
    novel_id: int,
    llm_config: dict | None = Depends(get_llm_config),
    body: BootstrapTriggerRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
    _quota_user: User = Depends(check_generation_quota),
):
    settings = get_settings()
    lock = await _get_bootstrap_trigger_lock(novel_id)

    async with lock:
        _get_novel(novel_id, db)
        decrement_quota(db, current_user, count=1)

        if not _has_non_empty_chapter_text(novel_id, db):
            raise HTTPException(
                status_code=400,
                detail=_error_detail(
                    "bootstrap_no_text",
                    "Novel has no non-empty chapter text to bootstrap",
                ),
            )

        job = db.query(BootstrapJob).filter(BootstrapJob.novel_id == novel_id).first()
        if job and is_running_status(job.status):
            if is_stale_running_job(
                job,
                stale_after_seconds=settings.bootstrap_stale_job_timeout_seconds,
            ):
                logger.warning(
                    "Reclaiming stale bootstrap job before retrigger",
                    extra={"novel_id": novel_id, "job_id": job.id, "status": job.status},
                )
            else:
                raise HTTPException(
                    status_code=409,
                    detail=_error_detail(
                        "bootstrap_already_running",
                        "Bootstrap already running for this novel",
                    ),
                )

        bootstrap_initialized = _is_bootstrap_initialized(job)
        mode, draft_policy = _resolve_trigger_params(
            body,
            bootstrap_initialized=bootstrap_initialized,
        )

        if (
            mode == BOOTSTRAP_MODE_REEXTRACT
            and draft_policy == BootstrapDraftPolicy.REPLACE_BOOTSTRAP_DRAFTS
        ):
            legacy = find_legacy_manual_draft_ambiguity(db, novel_id=novel_id)
            if legacy.has_any():
                _raise_legacy_ambiguity_conflict(
                    novel_id,
                    len(legacy.entity_ids),
                    len(legacy.relationship_ids),
                )

        if mode == BOOTSTRAP_MODE_INITIAL and bootstrap_initialized:
            raise HTTPException(
                status_code=409,
                detail=_error_detail(
                    "bootstrap_initial_mode_not_allowed",
                    "initial mode is only allowed before bootstrap initialization",
                ),
            )

        if not job:
            job = BootstrapJob(novel_id=novel_id)
            db.add(job)

        job.mode = mode
        job.draft_policy = draft_policy.value if draft_policy else None
        job.status = "pending"
        job.progress = {"step": 0, "detail": "queued"}
        job.result = {
            "entities_found": 0,
            "relationships_found": 0,
            "index_refresh_only": mode == BOOTSTRAP_MODE_INDEX_REFRESH,
        }
        job.error = None

        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing_job = db.query(BootstrapJob).filter(BootstrapJob.novel_id == novel_id).first()
            if existing_job and is_running_status(existing_job.status):
                raise HTTPException(
                    status_code=409,
                    detail=_error_detail(
                        "bootstrap_already_running",
                        "Bootstrap already running for this novel",
                    ),
                )
            raise HTTPException(
                status_code=409,
                detail=_error_detail(
                    "bootstrap_trigger_conflict",
                    "Bootstrap trigger conflict, please retry",
                ),
            )

        db.refresh(job)

        background_session_factory = sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)
        asyncio.create_task(
            run_bootstrap_job(
                job.id,
                session_factory=background_session_factory,
                user_id=current_user.id,
                llm_config=llm_config,
            )
        )

        return _serialize_bootstrap_job(job)


@router.get("/bootstrap/status", response_model=BootstrapJobResponse)
def get_bootstrap_status(
    novel_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    _get_novel(novel_id, db)
    job = db.query(BootstrapJob).filter(BootstrapJob.novel_id == novel_id).first()
    if not job:
        raise HTTPException(
            status_code=404,
            detail=_error_detail("bootstrap_job_not_found", "Bootstrap job not found"),
        )
    settings = get_settings()
    if is_stale_running_job(job, stale_after_seconds=settings.bootstrap_stale_job_timeout_seconds):
        job.status = "failed"
        job.error = "Bootstrap job stale after restart; please retry."
        db.commit()
        db.refresh(job)
    return _serialize_bootstrap_job(job)
