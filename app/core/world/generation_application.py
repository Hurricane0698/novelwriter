# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Application orchestration for text-to-world generation."""

from __future__ import annotations

import asyncio
import logging
import secrets
from typing import Awaitable, Callable

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.ai_client import LLMUnavailableError, StructuredOutputParseError
from app.core.events import ensure_project_start_event, record_event
from app.core.world.crud import load_novel
from app.core.world.gen import generate_world_drafts
from app.core.world.generation_runs import (
    claim_world_generation_run,
    complete_world_generation_run,
    fail_world_generation_run,
)
from app.core.world.use_case_errors import WorldUseCaseError, detail_error_from_http_exception
from app.core.auth import QuotaScope, ensure_ai_available
from app.core.llm_semaphore import acquire_llm_slot, release_llm_slot
from app.core.llm_config import ResolvedLlmConfig
from app.models import User
from app.schemas import WorldGenerateResponse

logger = logging.getLogger(__name__)
_world_generate_locks: dict[int, asyncio.Lock] = {}
_world_generate_locks_guard = asyncio.Lock()


def _world_generation_error_from_http_exception(exc: HTTPException) -> tuple[str, str]:
    if isinstance(exc.detail, dict):
        code = str(exc.detail.get("code") or "world_generate_failed")
        message = str(exc.detail.get("message") or code)
        return code[:64], message
    return "world_generate_failed", str(exc.detail)


def _world_generation_failure(
    exc: Exception,
    *,
    db: Session,
    run_id: int,
    claim_token: str,
    extra: dict | None = None,
) -> Exception:
    """Mark the durable run failed and translate `exc` into the use-case error.

    Single failure path so the refund/fail/raise invariant cannot drift between
    exception classes. Returns the exception the caller must raise.
    """
    if isinstance(exc, HTTPException):
        error_code, error_message = _world_generation_error_from_http_exception(exc)
        fail_world_generation_run(
            db,
            run_id=run_id,
            claim_token=claim_token,
            error_code=error_code,
            error_message=error_message,
        )
        return detail_error_from_http_exception(exc)

    if isinstance(exc, StructuredOutputParseError):
        logger.warning("world.generate invalid LLM output", exc_info=True, extra=extra)
        code, message, status_code = "world_generate_llm_schema_invalid", "LLM schema invalid", 502
    elif isinstance(exc, LLMUnavailableError):
        logger.warning("world.generate LLM unavailable", exc_info=True, extra=extra)
        code, message, status_code = "world_generate_llm_unavailable", "LLM unavailable", 503
    elif isinstance(exc, IntegrityError):
        code, message, status_code = "world_generate_conflict", "World generation conflict", 409
    else:
        logger.exception("world.generate failed", extra=extra)
        code, message, status_code = "world_generate_failed", "World generation failed", 500

    fail_world_generation_run(
        db,
        run_id=run_id,
        claim_token=claim_token,
        error_code=code,
        error_message=message,
    )
    return WorldUseCaseError(code=code, message=message, status_code=status_code)


async def generate_world_from_text(
    novel_id: int,
    *,
    text: str,
    db: Session,
    current_user: User,
    llm_config: ResolvedLlmConfig,
    request_id: str | None = None,
    generate_world_drafts_fn: Callable[..., Awaitable[WorldGenerateResponse]] | None = None,
    acquire_llm_slot_fn: Callable[[], Awaitable[None]] | None = None,
    release_llm_slot_fn: Callable[[], None] | None = None,
    record_event_fn: Callable[..., None] | None = None,
) -> WorldGenerateResponse:
    generation_runner = generate_world_drafts_fn or generate_world_drafts
    acquire_slot = acquire_llm_slot_fn or acquire_llm_slot
    release_slot = release_llm_slot_fn or release_llm_slot
    record_generate_event = record_event_fn or record_event

    load_novel(novel_id, db)
    claim_token = secrets.token_hex(16)
    run_claim = claim_world_generation_run(
        db,
        user_id=current_user.id,
        novel_id=novel_id,
        claim_token=claim_token,
    )
    if not run_claim.owner:
        raise WorldUseCaseError(
            code="world_generate_duplicate_request",
            message="World generation already running for this novel",
            status_code=409,
        )

    try:
        ensure_ai_available(
            db,
            billing_source=llm_config.billing_source_hint,
        )
    except HTTPException as exc:
        raise _world_generation_failure(
            exc,
            db=db,
            run_id=run_claim.run_id,
            claim_token=claim_token,
        ) from exc

    lock = await _get_world_generate_lock(novel_id)
    async with lock:
        extra = {
            "request_id": request_id,
            "novel_id": novel_id,
            "user_id": current_user.id,
        }

        slot_acquired = False
        try:
            await acquire_slot()
            slot_acquired = True
        except HTTPException as exc:
            raise _world_generation_failure(
                exc,
                db=db,
                run_id=run_claim.run_id,
                claim_token=claim_token,
                extra=extra,
            ) from exc

        # Durable reserve-then-refund: a crash between reserve and refund leaves
        # an open reservation row that reconciliation refunds, instead of
        # permanently losing user quota the way a bare decrement would.
        quota_scope = QuotaScope(db, current_user.id, count=1)
        try:
            try:
                quota_scope.reserve()
                result = await generation_runner(
                    db=db,
                    novel_id=novel_id,
                    text=text,
                    llm_config=llm_config,
                    user_id=current_user.id,
                )
                quota_scope.charge(1)
            except Exception as exc:
                raise _world_generation_failure(
                    exc,
                    db=db,
                    run_id=run_claim.run_id,
                    claim_token=claim_token,
                    extra=extra,
                ) from exc
            finally:
                quota_scope.finalize()
        finally:
            if slot_acquired:
                release_slot()

        complete_world_generation_run(
            db,
            run_id=run_claim.run_id,
            claim_token=claim_token,
        )
        ensure_project_start_event(
            db,
            user_id=current_user.id,
            novel_id=novel_id,
            start_mode="setting_import",
            meta={"entry_action": "world_generate"},
        )
        record_generate_event(
            db,
            current_user.id,
            "world_generate",
            novel_id=novel_id,
            meta={
                "entities_created": result.entities_created,
                "relationships_created": result.relationships_created,
                "systems_created": result.systems_created,
                "warnings_count": len(result.warnings),
            },
        )
        return result


async def _get_world_generate_lock(novel_id: int) -> asyncio.Lock:
    async with _world_generate_locks_guard:
        lock = _world_generate_locks.get(novel_id)
        if lock is None:
            lock = asyncio.Lock()
            _world_generate_locks[novel_id] = lock
        return lock
