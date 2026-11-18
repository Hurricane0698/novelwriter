# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.world_support import serialize_worldpack_import_result, translate_worldpack_import_error
from app.core.world.worldpack_import import WorldpackImportError, import_worldpack_payload
from app.database import get_db
from app.schemas import WorldpackImportResponse, WorldpackV1Payload

router = APIRouter()


@router.post("/worldpack/import", response_model=WorldpackImportResponse)
def import_worldpack_v1(
    novel_id: int,
    body: WorldpackV1Payload,
    db: Session = Depends(get_db),
):
    try:
        result = import_worldpack_payload(novel_id=novel_id, body=body, db=db)
    except WorldpackImportError as exc:
        raise translate_worldpack_import_error(exc)
    return serialize_worldpack_import_result(result)


__all__ = ["import_worldpack_v1", "router"]
