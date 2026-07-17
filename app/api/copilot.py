# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Copilot API endpoints.

All copilot endpoints live under /api/novels/{novel_id}/world/copilot/.
They are LLM endpoints and may receive BYOK headers.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import verify_novel_access
from app.core.auth import (
    check_generation_quota,
    finalize_quota_reservation,
    get_current_user_or_default,
    open_quota_reservation,
)
from app.core.copilot.apply import apply_suggestions
from app.core.copilot.runtime_errors import CopilotError
from app.core.copilot.run_state import check_stale_run
from app.core.copilot.runtime_lookup import load_latest_run, load_run, load_session
from app.core.copilot.service import (
    create_run,
    execute_copilot_run,
    open_or_reuse_session,
)
from app.core.copilot.session_runtime import list_session_runs
from app.core.copilot.suggestions import dismiss_suggestions
from app.core.events import record_event
from app.core.llm_request import get_llm_config
from app.core.llm_config import ResolvedLlmConfig
from app.database import get_db
from app.models import Novel, User
from app.schemas import (
    CopilotApplyActionResponse,
    CopilotApplyRequest,
    CopilotApplyResponse,
    CopilotApplyResultItem,
    CopilotDismissRequest,
    CopilotEvidenceResponse,
    CopilotFieldDeltaResponse,
    CopilotRunCreateRequest,
    CopilotRunResponse,
    CopilotSessionOpenRequest,
    CopilotSessionResponse,
    CopilotSuggestionPreviewResponse,
    CopilotSuggestionResponse,
    CopilotSuggestionTargetResponse,
    CopilotTraceStepResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/novels/{novel_id}/world/copilot", tags=["copilot"])


def _handle_copilot_error(exc: CopilotError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.message},
    )


def _copilot_session_event_meta(session, *, extra: dict[str, object] | None = None) -> dict[str, object]:
    meta: dict[str, object] = {
        "mode": getattr(session, "mode", ""),
        "scope": getattr(session, "scope", ""),
    }
    context = getattr(session, "context_json", None)
    if isinstance(context, dict):
        for key in ("surface", "stage", "tab"):
            value = context.get(key)
            if isinstance(value, str) and value.strip():
                meta[key] = value.strip()
    if extra:
        meta.update(extra)
    return meta


# ---------------------------------------------------------------------------
# Session endpoints
# ---------------------------------------------------------------------------


@router.post("/sessions", response_model=CopilotSessionResponse)
def session_open(
    novel_id: int,
    body: CopilotSessionOpenRequest,
    novel: Novel = Depends(verify_novel_access),
    user: User = Depends(get_current_user_or_default),
    db: Session = Depends(get_db),
):
    """Open or reuse a copilot session.

    If a session with the same (mode, scope, context, locale) already exists,
    it is reused.  Otherwise a new session is created.
    """
    try:
        context = body.context.model_dump() if body.context else None
        session, created = open_or_reuse_session(
            db=db,
            novel_id=novel_id,
            user_id=user.id,
            mode=body.mode,
            scope=body.scope,
            context=context,
            interaction_locale=body.interaction_locale,
            display_title=body.display_title,
        )
        return CopilotSessionResponse(
            session_id=session.session_id,
            signature=session.signature,
            mode=session.mode,
            scope=session.scope,
            context=session.context_json,
            interaction_locale=session.interaction_locale,
            display_title=session.display_title,
            created=created,
            created_at=session.created_at,
        )
    except CopilotError as exc:
        _handle_copilot_error(exc)


# ---------------------------------------------------------------------------
# Run endpoints
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/runs", response_model=CopilotRunResponse, status_code=202)
async def run_create(
    novel_id: int,
    session_id: str,
    body: CopilotRunCreateRequest,
    novel: Novel = Depends(verify_novel_access),
    user: User = Depends(check_generation_quota),
    llm_config: ResolvedLlmConfig = Depends(get_llm_config),
    db: Session = Depends(get_db),
):
    """Create a new copilot run.

    The run executes asynchronously.  Poll via GET to check progress.
    One non-terminal run per session; bounded active runs per user.
    """
    reservation_id: int | None = None
    try:
        session = load_session(db, novel_id, user.id, session_id)
        reservation_id = open_quota_reservation(db, user.id, count=1)
        try:
            run = create_run(
                db,
                session,
                user.id,
                body.prompt,
                quick_action_id=body.quick_action_id,
                resume_run_id=body.resume_run_id,
                quota_reservation_id=reservation_id,
            )
        except Exception:
            if reservation_id is not None:
                finalize_quota_reservation(db, reservation_id)
            raise
    except CopilotError as exc:
        _handle_copilot_error(exc)
        return  # unreachable, silences type checker

    # Spawn background execution
    asyncio.create_task(
        execute_copilot_run(
            run_id=run.run_id,
            novel_id=novel_id,
            user_id=user.id,
            llm_config=llm_config,
        )
    )

    record_event(
        db,
        user.id,
        "copilot_run",
        novel_id=novel_id,
        meta=_copilot_session_event_meta(
            session,
            extra={
                "quick_action_id": body.quick_action_id,
                "is_resume": body.resume_run_id is not None,
            },
        ),
    )

    return _run_to_response(run)


@router.get("/sessions/{session_id}/runs/{run_id}", response_model=CopilotRunResponse)
def run_poll(
    novel_id: int,
    session_id: str,
    run_id: str,
    novel: Novel = Depends(verify_novel_access),
    user: User = Depends(get_current_user_or_default),
    db: Session = Depends(get_db),
):
    """Poll a copilot run for current status and results."""
    try:
        run = load_run(db, novel_id, user.id, session_id, run_id)
    except CopilotError as exc:
        _handle_copilot_error(exc)
        return

    # Stale run detection: mark long-running runs as interrupted
    if check_stale_run(run):
        db.commit()

    return _run_to_response(run)


@router.get("/sessions/{session_id}/runs/latest", response_model=CopilotRunResponse)
def run_latest(
    novel_id: int,
    session_id: str,
    novel: Novel = Depends(verify_novel_access),
    user: User = Depends(get_current_user_or_default),
    db: Session = Depends(get_db),
):
    """Get the latest run for a session.

    Frontend can poll this without knowing run_id upfront.
    """
    try:
        session = load_session(db, novel_id, user.id, session_id)
        run = load_latest_run(db, session.id)
    except CopilotError as exc:
        _handle_copilot_error(exc)
        return

    if check_stale_run(run):
        db.commit()

    return _run_to_response(run)


@router.get("/sessions/{session_id}/runs", response_model=list[CopilotRunResponse])
def run_list(
    novel_id: int,
    session_id: str,
    novel: Novel = Depends(verify_novel_access),
    user: User = Depends(get_current_user_or_default),
    db: Session = Depends(get_db),
):
    """List all persisted runs in a session, oldest-first."""
    try:
        session = load_session(db, novel_id, user.id, session_id)
    except CopilotError as exc:
        _handle_copilot_error(exc)
        return

    runs = list_session_runs(db, session.id)
    for run in runs:
        if check_stale_run(run):
            db.commit()

    return [_run_to_response(run) for run in runs]


# ---------------------------------------------------------------------------
# Apply / Dismiss endpoints
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/runs/{run_id}/apply", response_model=CopilotApplyResponse)
def run_apply(
    novel_id: int,
    session_id: str,
    run_id: str,
    body: CopilotApplyRequest,
    novel: Novel = Depends(verify_novel_access),
    user: User = Depends(get_current_user_or_default),
    db: Session = Depends(get_db),
):
    """Apply selected suggestions from a completed run.

    Each suggestion is applied independently; one stale target does not block
    the rest.  Returns per-suggestion success/failure.
    """
    try:
        run = load_run(db, novel_id, user.id, session_id, run_id)
    except CopilotError as exc:
        _handle_copilot_error(exc)
        return

    if run.status != "completed":
        raise HTTPException(status_code=409, detail={"code": "run_not_completed", "message": "Run is not completed"})

    results = apply_suggestions(
        db,
        run,
        body.suggestion_ids,
        getattr(getattr(run, "session", None), "interaction_locale", "zh"),
    )
    success_count = sum(1 for result in results if result.success)
    record_event(
        db,
        user.id,
        "copilot_apply",
        novel_id=novel_id,
        meta=_copilot_session_event_meta(
            getattr(run, "session", None),
            extra={
                "requested_count": len(body.suggestion_ids),
                "success_count": success_count,
            },
        ),
    )
    return CopilotApplyResponse(
        results=[
            CopilotApplyResultItem(
                suggestion_id=r.suggestion_id,
                success=r.success,
                error_code=r.error_code,
                error_message=r.error_message,
            )
            for r in results
        ]
    )


@router.post("/sessions/{session_id}/runs/{run_id}/dismiss")
def run_dismiss(
    novel_id: int,
    session_id: str,
    run_id: str,
    body: CopilotDismissRequest,
    novel: Novel = Depends(verify_novel_access),
    user: User = Depends(get_current_user_or_default),
    db: Session = Depends(get_db),
):
    """Dismiss selected suggestions (no world-model mutation)."""
    try:
        run = load_run(db, novel_id, user.id, session_id, run_id)
    except CopilotError as exc:
        _handle_copilot_error(exc)
        return

    dismiss_suggestions(db, run, body.suggestion_ids)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------


def _run_to_response(run) -> CopilotRunResponse:
    trace = [
        CopilotTraceStepResponse(**step)
        for step in (run.trace_json or [])
    ]
    evidence = [
        CopilotEvidenceResponse(
            evidence_id=ev.get("evidence_id", ""),
            source_type=ev.get("source_type", ""),
            source_ref=ev.get("source_ref"),
            title=ev.get("title", ""),
            excerpt=ev.get("excerpt", ""),
            why_relevant=ev.get("why_relevant", ""),
            pack_id=ev.get("pack_id"),
            source_refs=ev.get("source_refs") or [],
            anchor_terms=ev.get("anchor_terms") or [],
            support_count=ev.get("support_count"),
            preview_excerpt=ev.get("preview_excerpt"),
            expanded=bool(ev.get("expanded", False)),
        )
        for ev in (run.evidence_json or [])
    ]
    suggestions = [
        _suggestion_to_response(sg)
        for sg in (run.suggestions_json or [])
    ]

    return CopilotRunResponse(
        run_id=run.run_id,
        status=run.status,
        prompt=run.prompt,
        answer=run.answer,
        trace=trace,
        evidence=evidence,
        suggestions=suggestions,
        error=run.error,
    )


def _suggestion_to_response(sg: dict) -> CopilotSuggestionResponse:
    target_data = sg.get("target", {})
    preview_data = sg.get("preview", {})
    apply_data = sg.get("apply")

    target = CopilotSuggestionTargetResponse(
        resource=target_data.get("resource", "entity"),
        resource_id=target_data.get("resource_id"),
        label=target_data.get("label", ""),
        tab=target_data.get("tab", "entities"),
        entity_id=target_data.get("entity_id"),
        review_kind=target_data.get("review_kind"),
        highlight_id=target_data.get("highlight_id"),
    )

    field_deltas = [
        CopilotFieldDeltaResponse(
            field=fd.get("field", ""),
            label=fd.get("label", ""),
            before=fd.get("before"),
            after=fd.get("after", ""),
        )
        for fd in preview_data.get("field_deltas", [])
    ]

    preview = CopilotSuggestionPreviewResponse(
        target_label=preview_data.get("target_label", ""),
        summary=preview_data.get("summary", ""),
        field_deltas=field_deltas,
        evidence_quotes=preview_data.get("evidence_quotes", []),
        actionable=preview_data.get("actionable", False),
        non_actionable_reason=preview_data.get("non_actionable_reason"),
    )

    apply_action = None
    if apply_data:
        apply_action = CopilotApplyActionResponse(
            type=apply_data.get("type", ""),
            entity_id=apply_data.get("entity_id"),
            relationship_id=apply_data.get("relationship_id"),
            system_id=apply_data.get("system_id"),
            data=apply_data.get("data", {}),
        )

    return CopilotSuggestionResponse(
        suggestion_id=sg.get("suggestion_id", ""),
        kind=sg.get("kind", ""),
        title=sg.get("title", ""),
        summary=sg.get("summary", ""),
        evidence_ids=sg.get("evidence_ids", []),
        target=target,
        preview=preview,
        apply=apply_action,
        status=sg.get("status", "pending"),
    )
