# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Session identity and run lookup helpers for copilot."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from sqlalchemy.orm import Session

from app.language import normalize_copilot_interaction_locale
from app.models import CopilotRun, CopilotSession

_ATLAS_STAGE_TABS = frozenset({"entities", "relationships", "systems", "review"})


def canonicalize_session_context(context: dict | None) -> dict[str, Any] | None:
    """Return the canonical stored UI context for a copilot session/run.

    Atlas continuity is tab-based. Legacy plural atlas stages are tolerated as
    aliases, then collapsed into ``tab`` so the stored contract stays
    surface-appropriate and frontend route label drift does not leak into
    durable runtime state.
    """
    if not context:
        return None

    normalized = {
        key: deepcopy(value) for key, value in context.items() if value is not None
    }
    if not normalized:
        return None

    raw_stage = normalized.get("stage")
    raw_tab = normalized.get("tab")
    if raw_tab is None and raw_stage in _ATLAS_STAGE_TABS:
        normalized["tab"] = raw_stage

    if normalized.get("surface") == "atlas" or raw_stage in _ATLAS_STAGE_TABS:
        normalized.pop("stage", None)

    return normalized or None


def normalize_session_identity_context(
    mode: str,
    scope: str,
    context: dict | None,
) -> dict[str, Any] | None:
    """Return the normalized session-identity context.

    Surface/stage are UI-only continuity hints and must not split the durable
    copilot session. Keep only the context fields that materially change the
    research workbench identity.
    """
    del mode
    context = canonicalize_session_context(context) or {}

    if context.get("text_target"):
        target = context["text_target"]
        return {"text_target": {"kind": target["kind"], "id": target["id"]}}

    if scope == "whole_book":
        return None

    if scope == "current_entity":
        entity_id = context.get("entity_id")
        if entity_id is None:
            return None
        return {"entity_id": entity_id}

    normalized: dict[str, Any] = {}
    tab = context.get("tab")
    if tab is not None:
        normalized["tab"] = tab
    entity_id = context.get("entity_id")
    if entity_id is not None:
        normalized["entity_id"] = entity_id

    return normalized or None


def build_session_signature(
    mode: str,
    scope: str,
    context: dict | None,
    interaction_locale: str,
) -> str:
    """Deterministic signature for session dedup."""
    normalized_context = normalize_session_identity_context(mode, scope, context)
    normalized_interaction_locale = normalize_copilot_interaction_locale(
        interaction_locale
    )
    payload = json.dumps(
        {
            "mode": mode,
            "scope": scope,
            "entity_id": (normalized_context or {}).get("entity_id"),
            "tab": (normalized_context or {}).get("tab"),
            "locale": normalized_interaction_locale,
            **({"text_target": normalized_context["text_target"]} if (normalized_context or {}).get("text_target") else {}),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def load_session(
    db: Session, novel_id: int, user_id: int, session_id: str
) -> CopilotSession | None:
    """Load session with strict novel + user scoping."""
    return (
        db.query(CopilotSession)
        .filter(
            CopilotSession.session_id == session_id,
            CopilotSession.novel_id == novel_id,
            CopilotSession.user_id == user_id,
        )
        .first()
    )


def load_run(
    db: Session, novel_id: int, user_id: int, session_id: str, run_id: str
) -> CopilotRun | None:
    """Load run with strict novel + user + session scoping."""
    return (
        db.query(CopilotRun)
        .join(CopilotSession, CopilotRun.copilot_session_id == CopilotSession.id)
        .filter(
            CopilotSession.session_id == session_id,
            CopilotSession.novel_id == novel_id,
            CopilotSession.user_id == user_id,
            CopilotRun.run_id == run_id,
        )
        .first()
    )


def load_latest_run(db: Session, copilot_session_id: int) -> CopilotRun | None:
    """Load the most recent run for a session (any status)."""
    return (
        db.query(CopilotRun)
        .filter(CopilotRun.copilot_session_id == copilot_session_id)
        .order_by(CopilotRun.created_at.desc(), CopilotRun.id.desc())
        .first()
    )


def list_session_runs(db: Session, copilot_session_id: int) -> list[CopilotRun]:
    """List session runs oldest-first for conversation/thread recovery."""
    return (
        db.query(CopilotRun)
        .filter(CopilotRun.copilot_session_id == copilot_session_id)
        .order_by(CopilotRun.created_at.asc(), CopilotRun.id.asc())
        .all()
    )


def build_follow_up_conversation_messages(
    prior_runs: list[CopilotRun],
) -> list[dict[str, str]]:
    """Convert prior completed runs into reusable user/assistant turns."""
    messages: list[dict[str, str]] = []
    for prior_run in prior_runs:
        if prior_run.status != "completed":
            continue
        prompt = (prior_run.prompt or "").strip()
        if prompt:
            messages.append({"role": "user", "content": prompt})
        answer = (prior_run.answer or "").strip()
        if answer:
            messages.append({"role": "assistant", "content": answer})
    return messages
