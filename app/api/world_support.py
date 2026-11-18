# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable, Literal, TypeVar

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.bootstrap import resolve_bootstrap_mode
from app.core.world.bootstrap_state import is_bootstrap_initialized
from app.core.world.crud import (
    WorldCrudDetailError,
    WorldCrudError,
    load_entity,
    load_novel,
    load_system,
)
from app.core.world.use_case_errors import WorldUseCaseDetailError, WorldUseCaseError
from app.core.world.worldpack_import import (
    UnsupportedWorldpackSchemaVersionError,
    WorldpackImportConflictError,
    WorldpackImportError,
    WorldpackImportResult,
    WorldpackNovelNotFoundError,
)
from app.models import BootstrapJob, Novel, WorldEntity, WorldSystem
from app.schemas import (
    BootstrapJobResponse,
    BootstrapMode,
    BootstrapProgress,
    BootstrapResult,
    WorldpackImportCounts,
    WorldpackImportResponse,
    WorldpackImportWarning,
)
from app.world_visibility import ALLOWED_VISIBILITIES, normalize_visibility

WorldModelRowStatus = Literal["draft", "confirmed"]
_T = TypeVar("_T")


def error_detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def parse_visibility_filter(visibility: str | None) -> str | None:
    if visibility is None:
        return None
    normalized = normalize_visibility(visibility)
    if not isinstance(normalized, str):
        raise HTTPException(
            status_code=422,
            detail=error_detail("invalid_visibility", "Invalid visibility"),
        )
    if normalized not in ALLOWED_VISIBILITIES:
        raise HTTPException(
            status_code=422,
            detail=error_detail("invalid_visibility", "Invalid visibility"),
        )
    return normalized


def translate_world_operation_error(exc: WorldCrudError | WorldUseCaseError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=error_detail(exc.code, exc.message))


def run_world_operation(operation: Callable[..., _T], /, *args, **kwargs) -> _T:
    try:
        return operation(*args, **kwargs)
    except (WorldCrudDetailError, WorldUseCaseDetailError) as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
            headers=getattr(exc, "headers", None),
        )
    except (WorldCrudError, WorldUseCaseError) as exc:
        raise translate_world_operation_error(exc)


async def run_world_operation_async(operation: Callable[..., object], /, *args, **kwargs):
    try:
        return await operation(*args, **kwargs)
    except (WorldCrudDetailError, WorldUseCaseDetailError) as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
            headers=getattr(exc, "headers", None),
        )
    except (WorldCrudError, WorldUseCaseError) as exc:
        raise translate_world_operation_error(exc)


def apply_ilike_search(query: Any, raw_query: str | None, *columns: Any):
    needle = (raw_query or "").strip()
    if not needle:
        return query
    like = f"%{needle}%"
    return query.filter(or_(*(column.ilike(like) for column in columns)))


def apply_exact_filters(query: Any, *filters: tuple[Any, Any]):
    for column, value in filters:
        if value is None or value == "":
            continue
        query = query.filter(column == value)
    return query


def get_novel(novel_id: int, db: Session) -> Novel:
    return run_world_operation(load_novel, novel_id, db)


def get_entity(novel_id: int, entity_id: int, db: Session) -> WorldEntity:
    return run_world_operation(load_entity, novel_id, entity_id, db)


def get_system(novel_id: int, system_id: int, db: Session) -> WorldSystem:
    return run_world_operation(load_system, novel_id, system_id, db)


def translate_worldpack_import_error(exc: WorldpackImportError) -> HTTPException:
    if isinstance(exc, WorldpackNovelNotFoundError):
        status_code = 404
    elif isinstance(exc, UnsupportedWorldpackSchemaVersionError):
        status_code = 400
    elif isinstance(exc, WorldpackImportConflictError):
        status_code = 409
    else:
        status_code = 400
    return HTTPException(status_code=status_code, detail=error_detail(exc.code, exc.message))


def serialize_worldpack_import_result(result: WorldpackImportResult) -> WorldpackImportResponse:
    return WorldpackImportResponse(
        pack_id=result.pack_id,
        counts=WorldpackImportCounts(**asdict(result.counts)),
        warnings=[WorldpackImportWarning(**asdict(warning)) for warning in result.warnings],
    )


def serialize_bootstrap_job(job: BootstrapJob) -> BootstrapJobResponse:
    progress = job.progress or {}
    result = job.result or {}
    mode = BootstrapMode(resolve_bootstrap_mode(getattr(job, "mode", None)))
    return BootstrapJobResponse(
        job_id=job.id,
        novel_id=job.novel_id,
        mode=mode,
        initialized=is_bootstrap_initialized(job),
        status=job.status,
        progress=BootstrapProgress(
            step=int(progress.get("step", 0)),
            detail=str(progress.get("detail", "")),
        ),
        result=BootstrapResult(
            entities_found=int(result.get("entities_found", 0)),
            relationships_found=int(result.get("relationships_found", 0)),
            index_refresh_only=bool(result.get("index_refresh_only", False)),
            llm_blocking_wait_seconds=float(result.get("llm_blocking_wait_seconds", 0.0) or 0.0),
            llm_blocking_wait_count=int(result.get("llm_blocking_wait_count", 0) or 0),
        ),
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


__all__ = [
    "WorldModelRowStatus",
    "apply_exact_filters",
    "apply_ilike_search",
    "error_detail",
    "get_entity",
    "get_novel",
    "get_system",
    "parse_visibility_filter",
    "run_world_operation",
    "run_world_operation_async",
    "serialize_bootstrap_job",
    "serialize_worldpack_import_result",
    "translate_world_operation_error",
    "translate_worldpack_import_error",
]
