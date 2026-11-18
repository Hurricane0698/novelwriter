# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Lookup and conflict helpers used by the copilot facade."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.copilot.run_state import ACTIVE_RUN_STATUSES
from app.core.copilot.runtime_errors import CopilotError
from app.core.copilot.session_runtime import (
    load_latest_run as _load_latest_run_record,
    load_run as _load_run_record,
    load_session as _load_session_record,
)
from app.models import CopilotRun, CopilotSession


def load_session_by_signature(
    db: Session,
    *,
    novel_id: int,
    user_id: int,
    signature: str,
) -> CopilotSession | None:
    return (
        db.query(CopilotSession)
        .filter(
            CopilotSession.novel_id == novel_id,
            CopilotSession.user_id == user_id,
            CopilotSession.signature == signature,
        )
        .first()
    )


def is_active_session_run_conflict(exc: IntegrityError) -> bool:
    message = str(getattr(exc, "orig", exc)).lower()
    return (
        "copilot_runs.copilot_session_id" in message
        or "uq_copilot_runs_active_session" in message
    )


def is_session_signature_conflict(exc: IntegrityError) -> bool:
    message = str(getattr(exc, "orig", exc)).lower()
    return (
        "copilot_sessions.novel_id, copilot_sessions.user_id, copilot_sessions.signature"
        in message
        or "uq_copilot_sessions_lookup" in message
    )


def count_active_runs(db: Session, user_id: int) -> int:
    return (
        db.query(CopilotRun)
        .filter(
            CopilotRun.user_id == user_id,
            CopilotRun.status.in_(tuple(ACTIVE_RUN_STATUSES)),
        )
        .count()
    )


def count_active_runs_in_session(db: Session, copilot_session_id: int) -> int:
    return (
        db.query(CopilotRun)
        .filter(
            CopilotRun.copilot_session_id == copilot_session_id,
            CopilotRun.status.in_(tuple(ACTIVE_RUN_STATUSES)),
        )
        .count()
    )


def load_session(
    db: Session,
    novel_id: int,
    user_id: int,
    session_id: str,
) -> CopilotSession:
    session = _load_session_record(db, novel_id, user_id, session_id)
    if session is None:
        raise CopilotError(
            code="session_not_found",
            message="Copilot session not found",
            status_code=404,
        )
    return session


def load_run(
    db: Session,
    novel_id: int,
    user_id: int,
    session_id: str,
    run_id: str,
) -> CopilotRun:
    run = _load_run_record(db, novel_id, user_id, session_id, run_id)
    if run is None:
        raise CopilotError(
            code="run_not_found",
            message="Copilot run not found",
            status_code=404,
        )
    return run


def load_latest_run(db: Session, copilot_session_id: int) -> CopilotRun:
    run = _load_latest_run_record(db, copilot_session_id)
    if run is None:
        raise CopilotError(
            code="run_not_found",
            message="No runs in this session",
            status_code=404,
        )
    return run
