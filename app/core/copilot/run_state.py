# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Run-state, lease, quota, and LLM parsing helpers for copilot."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session, object_session

from app.core.ai_client import AIClient
from app.core.auth import settle_quota_reservation
from app.core.copilot.messages import CopilotTextKey, get_copilot_text
from app.core.job_runtime import (
    is_stale_running_job,
    resolve_lease_expiry,
    utcnow_naive,
)
from app.language import normalize_copilot_interaction_locale
from app.models import CopilotRun

logger = logging.getLogger(__name__)

ACTIVE_RUN_STATUSES = frozenset({"queued", "running"})

# Queue and running leases share the same expiry rule; keep both names because
# call sites distinguish the two lease kinds.
resolve_queue_lease_expiry = resolve_lease_expiry
resolve_running_lease_expiry = resolve_lease_expiry


def resolve_run_interaction_locale(run: CopilotRun | None) -> str:
    if run is None:
        return "zh"
    session = getattr(run, "session", None)
    return normalize_copilot_interaction_locale(
        str(getattr(session, "interaction_locale", "zh") or "zh"),
    )


def copilot_run_failed_message(interaction_locale: str) -> str:
    return get_copilot_text(
        CopilotTextKey.RUN_FAILED,
        locale=interaction_locale,
    )


def copilot_run_interrupted_message(interaction_locale: str) -> str:
    return get_copilot_text(
        CopilotTextKey.RUN_INTERRUPTED,
        locale=interaction_locale,
    )


def running_trace_summary(interaction_locale: str) -> str:
    return get_copilot_text(
        CopilotTextKey.RUN_RESEARCHING,
        locale=interaction_locale,
    )


def run_settings():
    from app.config import get_settings

    return get_settings()


def is_active_run_status(status: str | None) -> bool:
    return status in ACTIVE_RUN_STATUSES


def ensure_run_lease(deps, db_factory, *, run_id: str, worker_id: str) -> None:
    """Renew the running lease or raise the deps' lease-lost error."""
    if (
        run_id
        and worker_id
        and db_factory
        and not deps.renew_run_lease(db_factory, run_id=run_id, worker_id=worker_id)
    ):
        raise deps.lease_lost_error_factory(run_id)


def interrupt_run(
    run: CopilotRun,
    *,
    message: str,
    now: datetime,
) -> None:
    run.status = "interrupted"
    run.error = message
    run.lease_owner = None
    run.lease_expires_at = None
    run.finished_at = now


def mark_run_error(
    run: CopilotRun,
    *,
    message: str,
    now: datetime,
) -> None:
    run.status = "error"
    run.error = message
    run.lease_owner = None
    run.lease_expires_at = None
    run.finished_at = now


def settle_run_quota(
    db: Session,
    run: CopilotRun,
    *,
    charge_count: int = 0,
) -> None:
    reservation_id = getattr(run, "quota_reservation_id", None)
    if reservation_id is None:
        return
    settle_quota_reservation(
        db, reservation_id, charge_count=charge_count, commit=False
    )


def settle_attached_run_quota(
    run: CopilotRun,
    *,
    charge_count: int = 0,
) -> None:
    db = object_session(run)
    if db is None:
        return
    settle_run_quota(db, run, charge_count=charge_count)


def is_stale_run(
    run: CopilotRun,
    *,
    now: datetime | None = None,
    stale_after_seconds: int | None = None,
) -> bool:
    if not is_active_run_status(run.status):
        return False

    stale_timeout = (
        run_settings().copilot_run_stale_timeout_seconds
        if stale_after_seconds is None
        else stale_after_seconds
    )
    return is_stale_running_job(
        status=run.status,
        running_status=run.status,
        lease_expires_at=run.lease_expires_at,
        updated_at=run.updated_at,
        created_at=run.created_at,
        stale_timeout_seconds=int(stale_timeout or 0),
        now=now,
    )


def reclaim_stale_runs(
    db: Session,
    *,
    run_ids: list[str] | None = None,
    user_id: int | None = None,
    copilot_session_id: int | None = None,
    message: str | None = None,
) -> list[str]:
    """Interrupt stale queued/running runs and return reclaimed run_ids."""
    query = db.query(CopilotRun).filter(
        CopilotRun.status.in_(tuple(ACTIVE_RUN_STATUSES))
    )
    if run_ids:
        query = query.filter(CopilotRun.run_id.in_(run_ids))
    if user_id is not None:
        query = query.filter(CopilotRun.user_id == user_id)
    if copilot_session_id is not None:
        query = query.filter(CopilotRun.copilot_session_id == copilot_session_id)

    now = utcnow_naive()
    reclaimed: list[str] = []
    for run in query.all():
        if not is_stale_run(run, now=now):
            continue
        logger.warning(
            "Reclaiming stale copilot run",
            extra={"run_id": run.run_id, "status": run.status, "user_id": run.user_id},
        )
        interrupt_run(
            run,
            message=message
            or copilot_run_interrupted_message(resolve_run_interaction_locale(run)),
            now=now,
        )
        settle_run_quota(db, run)
        reclaimed.append(run.run_id)

    if reclaimed:
        db.commit()

    return reclaimed


def claim_run_for_execution(
    db: Session,
    *,
    run_id: str,
    worker_id: str,
) -> CopilotRun | None:
    """Claim a queued run for one worker and move it to running."""
    run = db.query(CopilotRun).filter(CopilotRun.run_id == run_id).first()
    if run is None:
        return None
    if run.status != "queued":
        return None
    if is_stale_run(run):
        interrupt_run(
            run,
            message=copilot_run_interrupted_message(
                resolve_run_interaction_locale(run)
            ),
            now=utcnow_naive(),
        )
        settle_run_quota(db, run)
        db.commit()
        return None

    settings = run_settings()
    now = utcnow_naive()
    claimed = (
        db.query(CopilotRun)
        .filter(CopilotRun.run_id == run_id, CopilotRun.status == "queued")
        .update(
            {
                CopilotRun.status: "running",
                CopilotRun.error: None,
                CopilotRun.started_at: run.started_at or now,
                CopilotRun.finished_at: None,
                CopilotRun.lease_owner: worker_id,
                CopilotRun.lease_expires_at: resolve_running_lease_expiry(
                    now, settings.copilot_run_lease_seconds
                ),
                CopilotRun.trace_json: [
                    {
                        "step_id": "session_start",
                        "kind": "tool_mode",
                        "status": "running",
                        "summary": running_trace_summary(
                            resolve_run_interaction_locale(run)
                        ),
                    }
                ],
                CopilotRun.updated_at: now,
            },
            synchronize_session=False,
        )
    )
    if claimed != 1:
        db.rollback()
        return None
    db.commit()
    run = db.query(CopilotRun).filter(CopilotRun.run_id == run_id).first()
    if run is None:
        return None
    db.refresh(run)
    return run


def check_stale_run(run: CopilotRun) -> bool:
    """Check if an active run is stale and mark it interrupted. Returns True if stale."""
    if not is_stale_run(run):
        return False
    interrupt_run(
        run,
        message=copilot_run_interrupted_message(resolve_run_interaction_locale(run)),
        now=utcnow_naive(),
    )
    settle_attached_run_quota(run)
    return True


def extract_llm_kwargs(llm_config: dict[str, Any] | None) -> dict[str, Any]:
    """Extract LLM kwargs from config dict."""
    kwargs: dict[str, Any] = {}
    if llm_config:
        kwargs["base_url"] = llm_config.get("base_url")
        kwargs["api_key"] = llm_config.get("api_key")
        kwargs["model"] = llm_config.get("model")
        kwargs["billing_source_hint"] = llm_config.get(
            "billing_source_hint", "selfhost"
        )
    return kwargs


def fail_run(
    db: Session,
    run: CopilotRun,
    code: str,
    message: str,
    *,
    worker_id: str | None = None,
) -> None:
    del code
    if worker_id is not None and run.lease_owner != worker_id:
        logger.warning("Skipping fail_run for %s after lease loss", run.run_id)
        return
    mark_run_error(run, message=message, now=utcnow_naive())
    settle_run_quota(db, run)
    db.commit()


async def call_copilot_llm(
    system_prompt: str,
    user_prompt: str,
    llm_config: dict[str, Any] | None,
    user_id: int,
) -> str:
    client = AIClient()
    kwargs = extract_llm_kwargs(llm_config)
    return await client.generate(
        prompt=user_prompt,
        system_prompt=system_prompt,
        max_tokens=4000,
        temperature=0.4,
        role="default",
        user_id=user_id,
        **kwargs,
    )


def parse_llm_response(text: str) -> dict[str, Any]:
    """Parse the LLM's final response into structured output.

    Handles common LLM formatting quirks:
    1. Pure JSON
    2. JSON wrapped in ```json ... ``` code blocks (possibly with text before/after)
    3. Raw JSON object embedded in natural language text
    4. Fallback: treat entire text as the answer (no suggestions)

    Tool-call markup that a gateway returned as plain text (instead of a
    structured tool call) is stripped first so raw scaffolding never reaches the
    user-facing answer. The happy path (clean prose or answer JSON) is untouched.
    """
    import re

    from app.core.copilot.tool_call_recovery import (
        contains_tool_call_markup,
        strip_tool_call_markup,
    )

    if contains_tool_call_markup(text):
        text = strip_tool_call_markup(text)

    stripped = text.strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    code_block_match = re.search(
        r"```(?:json)?\s*\n(\{.*?\})\s*\n```", stripped, re.DOTALL
    )
    if code_block_match:
        try:
            return json.loads(code_block_match.group(1))
        except json.JSONDecodeError:
            pass

    first_brace = stripped.find("{")
    if first_brace != -1:
        candidate = stripped[first_brace:]
        for end in range(len(candidate), 1, -1):
            snippet = candidate[:end]
            try:
                return json.loads(snippet)
            except json.JSONDecodeError:
                continue

    return {"answer": text, "cited_evidence_indices": [], "suggestions": []}
