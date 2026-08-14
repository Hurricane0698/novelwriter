# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from dataclasses import dataclass
from typing import Any, List

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.core.auth import (
    QuotaScope,
    ensure_ai_available,
    reconcile_abandoned_quota_reservations,
)
from app.core.continuation_postcheck import postcheck_continuation
from app.core.continuation_runs import (
    CONTINUATION_RUN_STATUS_COMPLETED,
    CONTINUATION_RUN_STATUS_FAILED,
    CONTINUATION_RUN_REUSE_CLIENT_REQUEST,
    CONTINUATION_RUN_REUSE_SEMANTIC_ACTIVE,
    CONTINUATION_RUN_STATUS_RUNNING,
    ContinuationRunConflictError,
    build_continuation_request_hash,
    claim_continuation_run,
    complete_continuation_run,
    fail_continuation_run,
    normalize_continuation_client_request_id,
    record_continuation_run_result,
)
from app.core.events import record_event
from app.core.generator import continue_novel, continue_novel_stream
from app.core.llm_semaphore import acquire_llm_slot, release_llm_slot
from app.core.llm_config import ResolvedLlmConfig
from app.core.prose_check import prose_check_continuation
from app.models import Continuation, User
from app.schemas import ContinueDebugSummary, ContinueRequest, ContinueResponse

from . import novel_support
from .novel_continuation_context import _ContinuationContext, _prepare_continuation_context

logger = logging.getLogger(__name__)

_CONTINUATION_REQUEST_ID_HEADER = "x-novwr-continuation-request-id"
_CONTINUATION_ACTIVE_SEMANTIC_KEY = "continue"
_CONTINUATION_RUN_WAIT_TIMEOUT_SECONDS = 30.0
_CONTINUATION_RUN_WAIT_POLL_SECONDS = 0.1


@dataclass(frozen=True)
class _ContinuationRunResolution:
    client_request_id: str | None
    request_hash: str | None
    claim_token: str | None
    run_id: int | None
    owner: bool
    status: str | None
    reuse_kind: str | None
    delivered_count: int
    continuation_ids: tuple[int, ...]
    debug_summary: dict[str, Any] | None
    error_code: str | None
    error_message: str | None


def _normalize_continuation_request_id_from_headers(request: Request) -> str | None:
    try:
        return normalize_continuation_client_request_id(
            request.headers.get(_CONTINUATION_REQUEST_ID_HEADER)
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "continuation_request_id_invalid",
                "message": str(exc),
            },
        ) from exc


def _build_continuation_request_fingerprint(req: ContinueRequest) -> str:
    return build_continuation_request_hash(
        req.model_dump(mode="json", exclude_none=False)
    )


def _load_continuations_for_ids(
    db: Session,
    *,
    novel_id: int,
    continuation_ids: list[int],
) -> list[Continuation]:
    rows = (
        db.query(Continuation)
        .filter(Continuation.novel_id == novel_id, Continuation.id.in_(continuation_ids))
        .all()
    )
    by_id = {int(row.id): row for row in rows}
    missing = [item for item in continuation_ids if item not in by_id]
    if missing:
        raise RuntimeError(
            f"Stored continuation run referenced missing continuation ids: {missing}"
        )
    return [by_id[item] for item in continuation_ids]


def _build_continue_response_from_stored_run(
    db: Session,
    *,
    novel_id: int,
    continuation_ids: tuple[int, ...],
    debug_summary: dict[str, Any] | None,
) -> ContinueResponse:
    if not continuation_ids:
        raise RuntimeError("Completed continuation run had no persisted continuation ids")
    if not isinstance(debug_summary, dict):
        raise RuntimeError("Completed continuation run had no persisted debug summary")
    continuations = _load_continuations_for_ids(
        db,
        novel_id=novel_id,
        continuation_ids=list(continuation_ids),
    )
    return ContinueResponse(
        continuations=continuations,
        debug=ContinueDebugSummary.model_validate(debug_summary),
    )


async def _resolve_continuation_run(
    *,
    db: Session,
    request: Request,
    req: ContinueRequest,
    novel_id: int,
    user_id: int,
    wait_for_running: bool,
) -> _ContinuationRunResolution:
    client_request_id = (
        _normalize_continuation_request_id_from_headers(request)
        or f"implicit-{secrets.token_hex(16)}"
    )
    request_hash = _build_continuation_request_fingerprint(req)
    claim_token = secrets.token_hex(16)

    try:
        claim = claim_continuation_run(
            db,
            user_id=user_id,
            novel_id=novel_id,
            client_request_id=client_request_id,
            request_hash=request_hash,
            semantic_key=_CONTINUATION_ACTIVE_SEMANTIC_KEY,
            claim_token=claim_token,
        )
    except ContinuationRunConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "continuation_request_id_conflict",
                "message": str(exc),
            },
        ) from exc

    if (
        not wait_for_running
        or claim.owner
        or claim.status != CONTINUATION_RUN_STATUS_RUNNING
        or claim.reuse_kind != CONTINUATION_RUN_REUSE_CLIENT_REQUEST
    ):
        return _ContinuationRunResolution(
            client_request_id=client_request_id,
            request_hash=request_hash,
            claim_token=claim_token,
            run_id=claim.run_id,
            owner=claim.owner,
            status=claim.status,
            reuse_kind=claim.reuse_kind,
            delivered_count=claim.delivered_count,
            continuation_ids=claim.continuation_ids,
            debug_summary=claim.debug_summary,
            error_code=claim.error_code,
            error_message=claim.error_message,
        )

    deadline = asyncio.get_running_loop().time() + _CONTINUATION_RUN_WAIT_TIMEOUT_SECONDS
    latest = claim
    while asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(_CONTINUATION_RUN_WAIT_POLL_SECONDS)
        db.expire_all()
        latest = claim_continuation_run(
            db,
            user_id=user_id,
            novel_id=novel_id,
            client_request_id=client_request_id,
            request_hash=request_hash,
            semantic_key=_CONTINUATION_ACTIVE_SEMANTIC_KEY,
            claim_token=claim_token,
        )
        if latest.owner or latest.status != CONTINUATION_RUN_STATUS_RUNNING:
            break

    return _ContinuationRunResolution(
        client_request_id=client_request_id,
        request_hash=request_hash,
        claim_token=claim_token,
        run_id=latest.run_id,
        owner=latest.owner,
        status=latest.status,
        reuse_kind=latest.reuse_kind,
        delivered_count=latest.delivered_count,
        continuation_ids=latest.continuation_ids,
        debug_summary=latest.debug_summary,
        error_code=latest.error_code,
        error_message=latest.error_message,
    )


def _raise_for_stored_continuation_run_failure(
    resolution: _ContinuationRunResolution,
) -> None:
    raise HTTPException(
        status_code=409,
        detail={
            "code": resolution.error_code or "continuation_request_failed",
            "message": resolution.error_message or "Continuation request failed before completing",
        },
    )


def _raise_if_continuation_run_still_running(
    resolution: _ContinuationRunResolution,
) -> None:
    if resolution.reuse_kind == CONTINUATION_RUN_REUSE_SEMANTIC_ACTIVE:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "continuation_duplicate_request",
                "message": "Continuation already running for this novel",
            },
        )
    raise HTTPException(
        status_code=409,
        detail={
            "code": "continuation_request_still_running",
            "message": "Continuation request is still running; wait for the original run to finish",
        },
    )


def _maybe_prepare_continuation_quota(
    *,
    db: Session,
    current_user: User,
    billing_source: str,
) -> None:
    ensure_ai_available(db, billing_source=billing_source)
    if reconcile_abandoned_quota_reservations(db, user_id=current_user.id) > 0:
        try:
            db.refresh(current_user)
        except Exception:
            pass


def _continuation_run_error_from_http_exception(exc: HTTPException) -> tuple[str, str]:
    if isinstance(exc.detail, dict):
        code = str(exc.detail.get("code") or "continuation_request_failed")
        message = str(exc.detail.get("message") or code)
        return code[:64], message
    return "continuation_request_failed", str(exc.detail)


def _build_advisory_continuation_warning_update(
    *,
    writer_ctx: dict[str, Any],
    recent_text: str,
    user_prompt: str | None,
    continuations: List[Any],
    novel_language: str | None,
    novel_id: int,
    request_id: str | None = None,
) -> dict[str, Any]:
    update: dict[str, Any] = {}

    try:
        drift_warnings = postcheck_continuation(
            writer_ctx=writer_ctx,
            recent_text=recent_text,
            user_prompt=user_prompt,
            continuations=continuations,
            novel_language=novel_language,
        )
    except Exception:
        logger.warning(
            "continuation drift postcheck failed (request_id=%s, novel_id=%s)",
            request_id,
            novel_id,
            exc_info=True,
        )
    else:
        if drift_warnings:
            update["drift_warnings"] = drift_warnings

    try:
        prose_warnings = prose_check_continuation(
            continuations=continuations,
            novel_language=novel_language,
        )
    except Exception:
        logger.warning(
            "continuation prose postcheck failed (request_id=%s, novel_id=%s)",
            request_id,
            novel_id,
            exc_info=True,
        )
    else:
        if prose_warnings:
            update["prose_warnings"] = prose_warnings

    return update


def _has_claimed_run(resolution: _ContinuationRunResolution) -> bool:
    return resolution.run_id is not None and resolution.claim_token is not None


def _fail_claimed_run(
    db: Session,
    resolution: _ContinuationRunResolution,
    *,
    error_code: str,
    error_message: str,
) -> None:
    if not _has_claimed_run(resolution):
        return
    fail_continuation_run(
        db,
        run_id=resolution.run_id,
        claim_token=resolution.claim_token,
        error_code=error_code,
        error_message=error_message,
    )


def _complete_claimed_run(
    db: Session,
    resolution: _ContinuationRunResolution,
    *,
    continuation_ids: list[int],
    debug_summary: dict[str, Any],
) -> None:
    if not _has_claimed_run(resolution):
        return
    complete_continuation_run(
        db,
        run_id=resolution.run_id,
        claim_token=resolution.claim_token,
        continuation_ids=continuation_ids,
        debug_summary=debug_summary,
    )


async def _prepare_runtime_context(
    *,
    db: Session,
    novel_id: int,
    req: ContinueRequest,
    current_user: User,
    resolution: _ContinuationRunResolution,
    billing_source: str,
) -> _ContinuationContext:
    try:
        _maybe_prepare_continuation_quota(
            db=db,
            current_user=current_user,
            billing_source=billing_source,
        )
        return await run_in_threadpool(
            _prepare_continuation_context,
            db,
            novel_id,
            req,
            current_user,
        )
    except HTTPException as exc:
        error_code, error_message = _continuation_run_error_from_http_exception(exc)
        _fail_claimed_run(
            db,
            resolution,
            error_code=error_code,
            error_message=error_message,
        )
        raise
    except ValueError as exc:
        _fail_claimed_run(
            db,
            resolution,
            error_code="continuation_request_invalid",
            error_message=str(exc),
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _normalize_delivery_mode(request: Request) -> str:
    delivery_mode = (request.headers.get("x-novwr-delivery-mode") or "").strip().lower()
    if delivery_mode == "stream-fallback":
        return "stream_fallback"
    return "sync"


def _stream_replay_response(stored_response: ContinueResponse) -> StreamingResponse:
    debug_payload = stored_response.debug.model_dump()
    continuation_ids = [int(item.id) for item in stored_response.continuations]

    async def replay_existing_events():
        yield json.dumps(
            {
                "type": "start",
                "variant": 0,
                "total_variants": len(stored_response.continuations),
                "debug": debug_payload,
            },
            ensure_ascii=False,
        ) + "\n"
        for index, continuation in enumerate(stored_response.continuations):
            yield json.dumps(
                {
                    "type": "variant_done",
                    "variant": index,
                    "continuation_id": int(continuation.id),
                    "content": continuation.content,
                },
                ensure_ascii=False,
            ) + "\n"
        yield json.dumps(
            {
                "type": "done",
                "continuation_ids": continuation_ids,
                "debug": debug_payload,
            },
            ensure_ascii=False,
        ) + "\n"

    return StreamingResponse(
        replay_existing_events(),
        media_type="application/x-ndjson",
        headers=novel_support.STREAMING_RESPONSE_HEADERS,
    )


async def handle_continue_request(
    *,
    db: Session,
    novel_id: int,
    req: ContinueRequest,
    request: Request,
    current_user: User,
    llm_config: ResolvedLlmConfig,
) -> ContinueResponse:
    run_resolution = await _resolve_continuation_run(
        db=db,
        request=request,
        req=req,
        novel_id=novel_id,
        user_id=current_user.id,
        wait_for_running=True,
    )
    if not run_resolution.owner:
        if run_resolution.status == CONTINUATION_RUN_STATUS_COMPLETED:
            return _build_continue_response_from_stored_run(
                db,
                novel_id=novel_id,
                continuation_ids=run_resolution.continuation_ids,
                debug_summary=run_resolution.debug_summary,
            )
        if run_resolution.status == CONTINUATION_RUN_STATUS_FAILED:
            _raise_for_stored_continuation_run_failure(run_resolution)
        _raise_if_continuation_run_still_running(run_resolution)

    ctx = await _prepare_runtime_context(
        db=db,
        novel_id=novel_id,
        req=req,
        current_user=current_user,
        resolution=run_resolution,
        billing_source=llm_config.billing_source_hint,
    )

    quota = QuotaScope(db, current_user.id, count=int(req.num_versions or 1))
    slot_acquired = False
    quota_reserved = False
    try:
        await acquire_llm_slot()
        slot_acquired = True
        quota.reserve()
        quota_reserved = True
        continuations = await continue_novel(
            db=db,
            novel_id=novel_id,
            num_versions=req.num_versions,
            prompt=req.prompt,
            max_tokens=req.max_tokens,
            target_chars=req.target_chars,
            context_chapters=ctx.effective_context_chapters,
            chapter_recaps=ctx.chapter_recaps,
            world_context=ctx.world_context,
            narrative_constraints=ctx.narrative_constraints,
            world_debug_summary=ctx.debug_summary.model_dump(),
            llm_config=llm_config,
            temperature=req.temperature,
            user_id=current_user.id,
        )
        quota.charge(len(continuations or []))
    except ValueError as exc:
        _fail_claimed_run(
            db,
            run_resolution,
            error_code="continuation_request_invalid",
            error_message=str(exc),
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException as exc:
        error_code, error_message = _continuation_run_error_from_http_exception(exc)
        _fail_claimed_run(
            db,
            run_resolution,
            error_code=error_code,
            error_message=error_message,
        )
        raise
    except Exception:
        logger.exception("continue_novel failed for novel %s", novel_id)
        _fail_claimed_run(
            db,
            run_resolution,
            error_code="continuation_generation_failed",
            error_message="Continuation generation failed",
        )
        raise HTTPException(status_code=500, detail="Continuation generation failed")
    finally:
        if quota_reserved:
            quota.finalize()
        if slot_acquired:
            release_llm_slot()

    record_event(
        db,
        current_user.id,
        "generation",
        novel_id=novel_id,
        meta={
            "variants": len(continuations),
            "delivery_mode": _normalize_delivery_mode(request),
        },
    )

    warning_update = _build_advisory_continuation_warning_update(
        writer_ctx=ctx.writer_ctx,
        recent_text=ctx.recent_text,
        user_prompt=req.prompt,
        continuations=continuations,
        novel_language=ctx.novel_language,
        novel_id=novel_id,
    )
    if warning_update:
        ctx.debug_summary = ctx.debug_summary.model_copy(update=warning_update)

    _complete_claimed_run(
        db,
        run_resolution,
        continuation_ids=[int(item.id) for item in continuations],
        debug_summary=ctx.debug_summary.model_dump(),
    )

    return ContinueResponse(continuations=continuations, debug=ctx.debug_summary)


async def handle_continue_stream_request(
    *,
    db: Session,
    novel_id: int,
    req: ContinueRequest,
    request: Request,
    current_user: User,
    llm_config: ResolvedLlmConfig,
) -> StreamingResponse:
    run_resolution = await _resolve_continuation_run(
        db=db,
        request=request,
        req=req,
        novel_id=novel_id,
        user_id=current_user.id,
        wait_for_running=True,
    )
    if not run_resolution.owner:
        if run_resolution.status == CONTINUATION_RUN_STATUS_COMPLETED:
            stored_response = _build_continue_response_from_stored_run(
                db,
                novel_id=novel_id,
                continuation_ids=run_resolution.continuation_ids,
                debug_summary=run_resolution.debug_summary,
            )
            return _stream_replay_response(stored_response)
        if run_resolution.status == CONTINUATION_RUN_STATUS_FAILED:
            _raise_for_stored_continuation_run_failure(run_resolution)
        _raise_if_continuation_run_still_running(run_resolution)

    ctx = await _prepare_runtime_context(
        db=db,
        novel_id=novel_id,
        req=req,
        current_user=current_user,
        resolution=run_resolution,
        billing_source=llm_config.billing_source_hint,
    )

    request_id = getattr(request.state, "request_id", None)
    quota = QuotaScope(db, current_user.id, count=int(req.num_versions or 1))
    slot_acquired = False

    async def event_generator():
        nonlocal slot_acquired
        quota_reserved = False
        try:
            from types import SimpleNamespace

            await acquire_llm_slot()
            slot_acquired = True
            quota.reserve()
            quota_reserved = True

            contents_by_variant: dict[int, str] = {}
            total_variants: int | None = None

            async for event in continue_novel_stream(
                db=db,
                novel_id=novel_id,
                num_versions=req.num_versions,
                prompt=req.prompt,
                max_tokens=req.max_tokens,
                target_chars=req.target_chars,
                context_chapters=ctx.effective_context_chapters,
                chapter_recaps=ctx.chapter_recaps,
                world_context=ctx.world_context,
                narrative_constraints=ctx.narrative_constraints,
                world_debug_summary=ctx.debug_summary.model_dump(),
                llm_config=llm_config,
                request_id=request_id,
                temperature=req.temperature,
                user_id=current_user.id,
            ):
                if event.get("type") == "start":
                    try:
                        total_variants = int(event.get("total_variants") or req.num_versions)
                    except Exception:
                        total_variants = int(req.num_versions)

                if event.get("type") == "variant_done":
                    quota.charge(1)
                    try:
                        variant = int(event.get("variant"))
                        contents_by_variant[variant] = str(event.get("content") or "")
                        if _has_claimed_run(run_resolution):
                            record_continuation_run_result(
                                db,
                                run_id=run_resolution.run_id,
                                claim_token=run_resolution.claim_token,
                                continuation_id=int(event.get("continuation_id")),
                            )
                    except Exception:
                        pass

                if event.get("type") == "done":
                    variant_count = int(total_variants or req.num_versions)
                    continuations = [
                        SimpleNamespace(content=contents_by_variant.get(i, ""))
                        for i in range(variant_count)
                    ]
                    warning_update = _build_advisory_continuation_warning_update(
                        writer_ctx=ctx.writer_ctx,
                        recent_text=ctx.recent_text,
                        user_prompt=req.prompt,
                        continuations=continuations,
                        novel_language=ctx.novel_language,
                        novel_id=novel_id,
                        request_id=request_id,
                    )
                    debug_payload = ctx.debug_summary.model_dump()
                    if warning_update:
                        debug_with_warnings = ctx.debug_summary.model_copy(update=warning_update)
                        debug_payload = debug_with_warnings.model_dump()
                        event["debug"] = debug_payload
                    _complete_claimed_run(
                        db,
                        run_resolution,
                        continuation_ids=[int(item) for item in event.get("continuation_ids", [])],
                        debug_summary=debug_payload,
                    )
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except asyncio.CancelledError:
            _fail_claimed_run(
                db,
                run_resolution,
                error_code="continuation_stream_cancelled",
                error_message="Continuation stream was cancelled before completion",
            )
            raise
        except HTTPException as exc:
            error_code, error_message = _continuation_run_error_from_http_exception(exc)
            _fail_claimed_run(
                db,
                run_resolution,
                error_code=error_code,
                error_message=error_message,
            )
            raise
        except Exception:
            logger.exception("continue_novel_stream failed for novel %s", novel_id)
            _fail_claimed_run(
                db,
                run_resolution,
                error_code="continuation_stream_failed",
                error_message="Continuation stream failed",
            )
            raise
        finally:
            _fail_claimed_run(
                db,
                run_resolution,
                error_code="continuation_stream_interrupted",
                error_message="Continuation stream ended before completing",
            )
            if quota_reserved:
                quota.finalize()
            if quota.charged > 0:
                record_event(
                    db,
                    current_user.id,
                    "generation",
                    novel_id=novel_id,
                    meta={"variants": quota.charged, "stream": True, "delivery_mode": "stream"},
                )
            if slot_acquired:
                release_llm_slot()

    return StreamingResponse(
        event_generator(),
        media_type="application/x-ndjson",
        headers=novel_support.STREAMING_RESPONSE_HEADERS,
    )
