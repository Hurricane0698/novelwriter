# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Durable run progress and result persistence helpers for copilot."""

from __future__ import annotations

import logging
from typing import Callable

from sqlalchemy.orm import Session

from app.core.copilot.run_state import (
    resolve_running_lease_expiry,
    run_settings,
    settle_run_quota,
    utcnow_naive,
)
from app.core.copilot.scope import EvidenceItem, serialize_evidence
from app.core.copilot.suggestions import (
    CompiledSuggestion,
    serialize_compiled_suggestions,
)
from app.core.copilot.tracing import build_completed_trace, build_running_trace
from app.core.copilot.workspace import Workspace
from app.models import CopilotRun

logger = logging.getLogger(__name__)


def renew_run_lease(
    db_factory: Callable[[], Session],
    *,
    run_id: str,
    worker_id: str,
) -> bool:
    """Extend the lease of a running run. Returns False when ownership is lost."""
    db = db_factory()
    try:
        run = db.query(CopilotRun).filter(CopilotRun.run_id == run_id).first()
        if run is None or run.status != "running" or run.lease_owner != worker_id:
            return False
        run.lease_expires_at = resolve_running_lease_expiry(
            utcnow_naive(),
            run_settings().copilot_run_lease_seconds,
        )
        db.commit()
        return True
    finally:
        db.close()


def persist_preloaded_evidence(
    db: Session,
    run: CopilotRun,
    evidence: list[EvidenceItem],
) -> None:
    """Persist preloaded evidence and renew the running lease heartbeat."""
    run.evidence_json = [serialize_evidence(item) for item in evidence]
    run.lease_expires_at = resolve_running_lease_expiry(
        utcnow_naive(),
        run_settings().copilot_run_lease_seconds,
    )
    db.commit()


def persist_running_workspace(
    db_factory: Callable[[], Session],
    run_id: str,
    workspace: Workspace,
    *,
    worker_id: str = "",
) -> bool:
    """Persist workspace/progress to the active run row.

    Returns ``False`` only when the run disappeared or ownership was lost.
    Operational persistence failures degrade gracefully and return ``True`` so
    the runtime can continue without silently changing ownership semantics.
    """
    db = db_factory()
    try:
        ws_run = db.query(CopilotRun).filter(CopilotRun.run_id == run_id).first()
        if not ws_run:
            return False
        if worker_id and (ws_run.status != "running" or ws_run.lease_owner != worker_id):
            return False
        interaction_locale = getattr(getattr(ws_run, "session", None), "interaction_locale", "zh")

        ws_run.workspace_json = workspace.to_dict()
        ws_run.trace_json = build_running_trace(workspace, interaction_locale=interaction_locale)
        if worker_id:
            ws_run.lease_expires_at = resolve_running_lease_expiry(
                utcnow_naive(),
                run_settings().copilot_run_lease_seconds,
            )
        db.commit()
        return True
    except Exception:
        logger.warning("Failed to persist workspace for run %s", run_id, exc_info=True)
        return True
    finally:
        db.close()


def persist_completed_run(
    db_factory: Callable[[], Session],
    *,
    run_id: str,
    worker_id: str,
    answer: str,
    evidence: list[EvidenceItem],
    compiled_suggestions: list[CompiledSuggestion],
    workspace: Workspace | None,
    execution_mode: str,
    degraded_reason: str | None,
) -> bool:
    """Persist the terminal successful result for an owned running run."""
    db = db_factory()
    try:
        store_run = db.query(CopilotRun).filter(CopilotRun.run_id == run_id).first()
        if (
            not store_run
            or store_run.status != "running"
            or store_run.lease_owner != worker_id
        ):
            return False
        interaction_locale = getattr(getattr(store_run, "session", None), "interaction_locale", "zh")

        store_run.status = "completed"
        store_run.answer = answer
        store_run.evidence_json = [serialize_evidence(item) for item in evidence]
        store_run.suggestions_json = serialize_compiled_suggestions(compiled_suggestions)
        store_run.trace_json = build_completed_trace(
            workspace=workspace,
            execution_mode=execution_mode,
            degraded_reason=degraded_reason,
            evidence_count=len(evidence),
            suggestion_count=len(compiled_suggestions),
            interaction_locale=interaction_locale,
        )
        store_run.error = None
        store_run.lease_owner = None
        store_run.lease_expires_at = None
        store_run.finished_at = utcnow_naive()
        if workspace:
            store_run.workspace_json = workspace.to_dict()
        settle_run_quota(db, store_run, charge_count=1)
        db.commit()
        return True
    finally:
        db.close()
