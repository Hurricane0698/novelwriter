# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Application orchestration for text-to-world generation."""

from __future__ import annotations

import asyncio
import logging
import secrets
from typing import Callable

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.ai_client import LLMUnavailableError, StructuredOutputParseError
from app.core.world.crud import load_novel
from app.core.world.gen import generate_world_drafts
from app.core.world.generation_runs import (
    claim_world_generation_run,
    complete_world_generation_run,
    fail_world_generation_run,
)
from app.core.world.use_case_errors import WorldUseCaseError, detail_error_from_http_exception
from app.core.llm_semaphore import acquire_llm_slot, release_llm_slot
from app.core.llm_config import ResolvedLlmConfig
from app.schemas import WorldGenerateResponse

logger = logging.getLogger(__name__)


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

    if isinstance(exc, WorldUseCaseError):
        code, message, status_code = exc.code, exc.message, exc.status_code
    elif isinstance(exc, StructuredOutputParseError):
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
    session_factory: Callable[[], Session],
    user_id: int,
    llm_config: ResolvedLlmConfig,
    request_id: str | None = None,
) -> WorldGenerateResponse:
    claim_token = secrets.token_hex(16)
    with session_factory() as db:
        load_novel(novel_id, db)
        run_id = claim_world_generation_run(
            db, user_id=user_id, novel_id=novel_id, claim_token=claim_token,
        )
        if run_id is None:
            raise WorldUseCaseError(
                code="world_generate_duplicate_request",
                message="World generation already running for this novel", status_code=409,
            )
    extra = {"request_id": request_id, "novel_id": novel_id, "user_id": user_id}
    slot_acquired = False
    try:
        await acquire_llm_slot()
        slot_acquired = True
        result = await generate_world_drafts(
            session_factory=session_factory, novel_id=novel_id, text=text,
            llm_config=llm_config, user_id=user_id,
        )
        with session_factory() as db:
            complete_world_generation_run(db, run_id=run_id, claim_token=claim_token)
        return result
    except asyncio.CancelledError:
        with session_factory() as db:
            fail_world_generation_run(
                db, run_id=run_id, claim_token=claim_token,
                error_code="world_generate_cancelled", error_message="World generation cancelled",
            )
        raise
    except Exception as exc:
        with session_factory() as db:
            raise _world_generation_failure(
                exc, db=db, run_id=run_id, claim_token=claim_token, extra=extra,
            ) from exc
    finally:
        if slot_acquired:
            release_llm_slot()
