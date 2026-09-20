# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Session/run lifecycle helpers for copilot facade modules."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.copilot.run_state import (
    reclaim_stale_runs,
    resolve_queue_lease_expiry,
    run_settings,
    utcnow_naive,
)
from app.core.copilot.session_runtime import (
    build_session_signature,
    canonicalize_session_context,
)
from app.language import normalize_copilot_interaction_locale
from app.models import CopilotRun, CopilotSession


@dataclass(frozen=True)
class SessionLifecycleHooks:
    load_session_by_signature: Callable[..., CopilotSession | None]
    is_session_signature_conflict: Callable[[IntegrityError], bool]
    copilot_error_factory: Callable[[str, str, int], Exception]


@dataclass(frozen=True)
class RunLifecycleHooks:
    count_active_runs: Callable[[Session, int], int]
    count_active_runs_in_session: Callable[[Session, int], int]
    is_active_session_run_conflict: Callable[[IntegrityError], bool]
    copilot_error_factory: Callable[[str, str, int], Exception]


def open_or_reuse_session(
    *,
    hooks: SessionLifecycleHooks,
    db: Session,
    novel_id: int,
    user_id: int,
    mode: str,
    scope: str,
    context: dict | None,
    interaction_locale: str,
    display_title: str,
) -> tuple[CopilotSession, bool]:
    """Return (session, created). Reuse by canonical session signature."""
    context = canonicalize_session_context(context)
    normalized_interaction_locale = normalize_copilot_interaction_locale(
        interaction_locale
    )
    signature = build_session_signature(
        mode,
        scope,
        context,
        normalized_interaction_locale,
    )

    existing = hooks.load_session_by_signature(
        db,
        novel_id=novel_id,
        user_id=user_id,
        signature=signature,
    )
    if existing is not None:
        existing.last_active_at = func.now()
        existing.context_json = context
        existing.interaction_locale = normalized_interaction_locale
        if display_title:
            existing.display_title = display_title
        db.commit()
        db.refresh(existing)
        return existing, False

    session = CopilotSession(
        session_id=str(uuid.uuid4()),
        novel_id=novel_id,
        user_id=user_id,
        mode=mode,
        scope=scope,
        context_json=context,
        interaction_locale=normalized_interaction_locale,
        signature=signature,
        display_title=display_title or "",
    )
    db.add(session)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if not hooks.is_session_signature_conflict(exc):
            raise hooks.copilot_error_factory(
                "copilot_session_conflict",
                "Copilot session creation conflict, please retry",
                409,
            ) from exc

        existing = hooks.load_session_by_signature(
            db,
            novel_id=novel_id,
            user_id=user_id,
            signature=signature,
        )
        if existing is None:
            raise hooks.copilot_error_factory(
                "copilot_session_conflict",
                "Copilot session creation conflict, please retry",
                409,
            ) from exc
        existing.last_active_at = func.now()
        existing.context_json = context
        if display_title:
            existing.display_title = display_title
        db.commit()
        db.refresh(existing)
        return existing, False

    db.refresh(session)
    return session, True


def create_run(
    *,
    hooks: RunLifecycleHooks,
    db: Session,
    session: CopilotSession,
    user_id: int,
    prompt: str,
    quick_action_id: str | None = None,
    resume_run_id: str | None = None,
    quota_reservation_id: int | None = None,
) -> CopilotRun:
    """Create a new run while enforcing active-run admission limits."""
    settings = run_settings()
    reclaim_stale_runs(db)
    run_context = canonicalize_session_context(session.context_json)
    from app.core.copilot.text_review_evidence import TEXT_REVIEW_ACTIONS, bind_text_target
    if (run_context or {}).get("text_target"):
        quick_action_id = quick_action_id if quick_action_id in TEXT_REVIEW_ACTIONS else "review_text"
        run_context["text_target"] = bind_text_target(db, session.novel_id, run_context["text_target"])
    elif quick_action_id in TEXT_REVIEW_ACTIONS:
        raise hooks.copilot_error_factory("text_target_required", "请选择要核对的正文或候选。", 422)

    if (
        hooks.count_active_runs_in_session(db, session.id)
        >= settings.copilot_max_runs_per_session
    ):
        raise hooks.copilot_error_factory(
            "session_run_active",
            "Session already has an active run",
            409,
        )

    copilot_user_limit = settings.copilot_max_runs_per_user
    if hooks.count_active_runs(db, user_id) >= copilot_user_limit:
        raise hooks.copilot_error_factory(
            "too_many_active_runs",
            f"Too many active copilot runs (max {copilot_user_limit})",
            429,
        )

    global_limit = settings.copilot_max_runs_global
    global_active = (
        db.query(CopilotRun)
        .filter(CopilotRun.status.in_(("queued", "running")))
        .count()
    )
    if global_active >= global_limit:
        raise hooks.copilot_error_factory(
            "too_many_global_runs",
            f"Server busy — too many copilot runs (max {global_limit})",
            503,
        )

    inherited_workspace = None
    if resume_run_id:
        resume_run = (
            db.query(CopilotRun)
            .filter(
                CopilotRun.copilot_session_id == session.id,
                CopilotRun.user_id == user_id,
                CopilotRun.run_id == resume_run_id,
            )
            .first()
        )
        if resume_run is None:
            raise hooks.copilot_error_factory(
                "resume_run_not_found",
                "Interrupted run to resume was not found",
                404,
            )
        if resume_run.status != "interrupted":
            raise hooks.copilot_error_factory(
                "resume_run_not_interrupted",
                "Only interrupted runs can be resumed",
                409,
            )
        if (resume_run.prompt or "").strip() != prompt.strip():
            raise hooks.copilot_error_factory(
                "resume_prompt_mismatch",
                "Resume prompt must match the interrupted run prompt",
                409,
            )
        if not resume_run.workspace_json or not resume_run.workspace_json.get(
            "messages"
        ):
            raise hooks.copilot_error_factory(
                "resume_run_not_resumable",
                "Interrupted run has no resumable workspace",
                409,
            )
        inherited_workspace = resume_run.workspace_json

    now = utcnow_naive()
    run = CopilotRun(
        run_id=str(uuid.uuid4()),
        copilot_session_id=session.id,
        novel_id=session.novel_id,
        user_id=user_id,
        quota_reservation_id=quota_reservation_id,
        quick_action_id=quick_action_id,
        status="queued",
        prompt=prompt,
        context_json=run_context,
        trace_json=[],
        evidence_json=[],
        suggestions_json=[],
        workspace_json=inherited_workspace,
        lease_owner=None,
        lease_expires_at=resolve_queue_lease_expiry(
            now, settings.copilot_run_queue_timeout_seconds
        ),
        started_at=None,
        finished_at=None,
    )
    db.add(run)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if (
            hooks.is_active_session_run_conflict(exc)
            or hooks.count_active_runs_in_session(db, session.id)
            >= settings.copilot_max_runs_per_session
        ):
            raise hooks.copilot_error_factory(
                "session_run_active",
                "Session already has an active run",
                409,
            ) from exc
        raise hooks.copilot_error_factory(
            "copilot_run_conflict",
            "Copilot run creation conflict, please retry",
            409,
        ) from exc

    db.refresh(run)
    return run
