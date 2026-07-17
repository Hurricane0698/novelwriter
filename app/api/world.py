# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import verify_novel_access
from app.api.world_bootstrap import (
    get_bootstrap_status,
    router as bootstrap_router,
    trigger_bootstrap,
)
from app.api.world_entities import (
    add_attribute,
    batch_confirm_entities,
    batch_reject_entities,
    create_entity,
    delete_attribute,
    delete_entity,
    get_entity,
    list_entities,
    reorder_attributes,
    router as entities_router,
    update_attribute,
    update_entity,
)
from app.api.world_generation import generate_world_from_text, router as generation_router
from app.api.world_import import import_worldpack_v1, router as import_router
from app.api.world_relationships import (
    batch_confirm_relationships,
    batch_reject_relationships,
    create_relationship,
    delete_relationship,
    list_relationships,
    router as relationships_router,
    update_relationship,
)
from app.api.world_support import serialize_bootstrap_job
from app.api.world_systems import (
    batch_confirm_systems,
    batch_reject_systems,
    create_system,
    delete_system,
    get_system,
    list_systems,
    router as systems_router,
    update_system,
)
from app.core.auth import get_current_user_or_default

router = APIRouter(
    prefix="/api/novels/{novel_id}/world",
    tags=["world"],
    dependencies=[Depends(verify_novel_access)],
)
router.include_router(entities_router)
router.include_router(relationships_router)
router.include_router(systems_router)
router.include_router(import_router)
router.include_router(generation_router)
router.include_router(bootstrap_router)

_serialize_bootstrap_job = serialize_bootstrap_job

__all__ = [
    "_serialize_bootstrap_job",
    "add_attribute",
    "batch_confirm_entities",
    "batch_confirm_relationships",
    "batch_confirm_systems",
    "batch_reject_entities",
    "batch_reject_relationships",
    "batch_reject_systems",
    "create_entity",
    "create_relationship",
    "create_system",
    "delete_attribute",
    "delete_entity",
    "delete_relationship",
    "delete_system",
    "generate_world_from_text",
    "get_bootstrap_status",
    "get_current_user_or_default",
    "get_entity",
    "get_system",
    "import_worldpack_v1",
    "list_entities",
    "list_relationships",
    "list_systems",
    "reorder_attributes",
    "router",
    "trigger_bootstrap",
    "update_attribute",
    "update_entity",
    "update_relationship",
    "update_system",
]
