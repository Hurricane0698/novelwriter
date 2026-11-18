# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.models import BootstrapJob

DEFAULT_STALE_JOB_TIMEOUT_SECONDS = 900
BOOTSTRAP_RESULT_QUEUED_USER_ID_KEY = "_queued_user_id"
BOOTSTRAP_RESULT_QUEUED_SOURCE_KEY = "_queued_source"
BOOTSTRAP_RESULT_QUEUED_SOURCE_INGEST_AUTO = "ingest_auto"
BOOTSTRAP_MODE_INITIAL = "initial"
BOOTSTRAP_MODE_INDEX_REFRESH = "index_refresh"
BOOTSTRAP_MODE_REEXTRACT = "reextract"
BOOTSTRAP_DRAFT_POLICY_REPLACE_BOOTSTRAP_DRAFTS = "replace_bootstrap_drafts"
BOOTSTRAP_DRAFT_POLICY_MERGE = "merge"

BOOTSTRAP_STATUS_SEQUENCE = (
    "pending",
    "tokenizing",
    "extracting",
    "windowing",
    "refining",
    "completed",
)
RUNNING_BOOTSTRAP_STATUSES = frozenset(BOOTSTRAP_STATUS_SEQUENCE[:-1])

_ALLOWED_TRANSITIONS = {
    "pending": {"tokenizing", "failed"},
    "tokenizing": {"extracting", "failed"},
    "extracting": {"windowing", "failed"},
    "windowing": {"refining", "failed"},
    "refining": {"completed", "failed"},
    "completed": set(),
    "failed": set(),
}

_KNOWN_BOOTSTRAP_MODES = frozenset(
    {
        BOOTSTRAP_MODE_INITIAL,
        BOOTSTRAP_MODE_INDEX_REFRESH,
        BOOTSTRAP_MODE_REEXTRACT,
    }
)
_KNOWN_REEXTRACT_DRAFT_POLICIES = frozenset(
    {
        BOOTSTRAP_DRAFT_POLICY_REPLACE_BOOTSTRAP_DRAFTS,
        BOOTSTRAP_DRAFT_POLICY_MERGE,
    }
)


@dataclass(slots=True)
class LegacyDraftAmbiguity:
    entity_ids: list[int]
    relationship_ids: list[int]

    def has_any(self) -> bool:
        return bool(self.entity_ids or self.relationship_ids)


@dataclass(slots=True)
class BootstrapRunSummary:
    novel_id: int
    mode: str
    entities_found: int
    relationships_found: int


def is_running_status(status: str | None) -> bool:
    return status in RUNNING_BOOTSTRAP_STATUSES


def resolve_bootstrap_mode(raw_mode: str | None) -> str:
    mode = (raw_mode or BOOTSTRAP_MODE_INDEX_REFRESH).strip()
    if mode in _KNOWN_BOOTSTRAP_MODES:
        return mode
    return BOOTSTRAP_MODE_INDEX_REFRESH


def resolve_reextract_draft_policy(raw_policy: str | None) -> str:
    policy = (raw_policy or BOOTSTRAP_DRAFT_POLICY_REPLACE_BOOTSTRAP_DRAFTS).strip()
    if policy in _KNOWN_REEXTRACT_DRAFT_POLICIES:
        return policy
    return BOOTSTRAP_DRAFT_POLICY_REPLACE_BOOTSTRAP_DRAFTS


def is_stale_running_job(
    job: BootstrapJob,
    *,
    stale_after_seconds: int = DEFAULT_STALE_JOB_TIMEOUT_SECONDS,
    now: datetime | None = None,
) -> bool:
    if stale_after_seconds <= 0:
        return False
    if not is_running_status(job.status):
        return False

    updated_at = job.updated_at or job.created_at
    if updated_at is None:
        return False

    if updated_at.tzinfo is not None:
        updated_at = updated_at.astimezone(timezone.utc).replace(tzinfo=None)

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is not None:
        current_time = current_time.astimezone(timezone.utc).replace(tzinfo=None)

    return updated_at <= (current_time - timedelta(seconds=stale_after_seconds))


def transition_bootstrap_job(
    job: BootstrapJob,
    new_status: str,
    *,
    detail: str | None = None,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    current = str(job.status)
    allowed = _ALLOWED_TRANSITIONS.get(current)
    if allowed is None:
        raise ValueError(f"Unknown bootstrap status: {current}")
    if new_status not in allowed:
        raise ValueError(f"Invalid bootstrap transition: {current} -> {new_status}")

    current_progress = job.progress or {}
    if new_status in BOOTSTRAP_STATUS_SEQUENCE:
        step = BOOTSTRAP_STATUS_SEQUENCE.index(new_status)
    else:
        step = int(current_progress.get("step", 0))

    job.status = new_status
    job.progress = {
        **current_progress,
        "step": step,
        "detail": detail or new_status,
    }

    if new_status == "completed":
        current_result = dict(job.result or {})
        job.result = {
            **current_result,
            "entities_found": 0,
            "relationships_found": 0,
            "index_refresh_only": False,
            "llm_blocking_wait_seconds": float(current_result.get("llm_blocking_wait_seconds", 0.0) or 0.0),
            "llm_blocking_wait_count": int(current_result.get("llm_blocking_wait_count", 0) or 0),
            **(result or {}),
        }
        job.error = None
    elif new_status == "failed":
        job.error = error or "Bootstrap failed"


def build_bootstrap_trigger_result(
    *,
    mode: str,
    user_id: int | None = None,
    queued_source: str | None = None,
) -> dict[str, int | bool | str]:
    result: dict[str, int | bool | str] = {
        "entities_found": 0,
        "relationships_found": 0,
        "index_refresh_only": resolve_bootstrap_mode(mode) == BOOTSTRAP_MODE_INDEX_REFRESH,
    }
    if user_id is not None:
        result[BOOTSTRAP_RESULT_QUEUED_USER_ID_KEY] = int(user_id)
    if queued_source is not None:
        result[BOOTSTRAP_RESULT_QUEUED_SOURCE_KEY] = queued_source
    return result


def bootstrap_job_queued_source(job: BootstrapJob) -> str | None:
    raw_result = job.result or {}
    raw_source = raw_result.get(BOOTSTRAP_RESULT_QUEUED_SOURCE_KEY)
    if not isinstance(raw_source, str):
        return None
    normalized = raw_source.strip()
    return normalized or None


def resolve_bootstrap_trigger_user_id(job: BootstrapJob) -> int | None:
    raw_result = job.result or {}
    raw_user_id = raw_result.get(BOOTSTRAP_RESULT_QUEUED_USER_ID_KEY)
    if raw_user_id is None:
        return None
    try:
        user_id = int(raw_user_id)
    except (TypeError, ValueError):
        return None
    return user_id if user_id > 0 else None


__all__ = [
    "BOOTSTRAP_DRAFT_POLICY_MERGE",
    "BOOTSTRAP_DRAFT_POLICY_REPLACE_BOOTSTRAP_DRAFTS",
    "BOOTSTRAP_MODE_INDEX_REFRESH",
    "BOOTSTRAP_MODE_INITIAL",
    "BOOTSTRAP_MODE_REEXTRACT",
    "BOOTSTRAP_RESULT_QUEUED_SOURCE_INGEST_AUTO",
    "BOOTSTRAP_RESULT_QUEUED_SOURCE_KEY",
    "BOOTSTRAP_RESULT_QUEUED_USER_ID_KEY",
    "BOOTSTRAP_STATUS_SEQUENCE",
    "BootstrapRunSummary",
    "DEFAULT_STALE_JOB_TIMEOUT_SECONDS",
    "LegacyDraftAmbiguity",
    "RUNNING_BOOTSTRAP_STATUSES",
    "bootstrap_job_queued_source",
    "build_bootstrap_trigger_result",
    "is_running_status",
    "is_stale_running_job",
    "resolve_bootstrap_mode",
    "resolve_bootstrap_trigger_user_id",
    "resolve_reextract_draft_policy",
    "transition_bootstrap_job",
]
