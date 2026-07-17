from __future__ import annotations

from app.config import Settings, get_settings
from app.core.indexing.planner import (
    AUTO_INDEX_PLAN_DEFERRED,
    AUTO_INDEX_PLAN_IMMEDIATE,
    AUTO_INDEX_PLAN_SKIP_AUTO,
)

from .contracts import IngestPolicyDecision, IngestPolicyInput

_MEBIBYTE = 1024 * 1024


def _meets_threshold(value: int, *, threshold: int) -> bool:
    normalized = max(int(value or 0), 0)
    normalized_threshold = max(int(threshold or 0), 0)
    return normalized_threshold > 0 and normalized >= normalized_threshold


def upload_limit_bytes(settings: Settings) -> int:
    return max(int(settings.upload_max_megabytes or 0), 1) * _MEBIBYTE


def resolve_ingest_policy(
    policy_input: IngestPolicyInput,
    *,
    settings: Settings | None = None,
) -> IngestPolicyDecision:
    resolved_settings = settings or get_settings()
    if max(int(policy_input.source_bytes or 0), 0) > upload_limit_bytes(resolved_settings):
        return IngestPolicyDecision(
            size_tier="reject",
            auto_index_plan=AUTO_INDEX_PLAN_SKIP_AUTO,
            bootstrap_plan="manual_only",
            readiness_mode="degraded_target",
        )

    is_large = any(
        (
            _meets_threshold(
                policy_input.source_bytes,
                threshold=int(resolved_settings.ingest_large_source_bytes or 0),
            ),
            _meets_threshold(
                policy_input.source_chars,
                threshold=int(resolved_settings.ingest_large_source_chars or 0),
            ),
            _meets_threshold(
                policy_input.chapter_count,
                threshold=int(resolved_settings.ingest_large_chapter_count or 0),
            ),
        )
    )

    if not is_large:
        return IngestPolicyDecision(
            size_tier="normal",
            auto_index_plan=AUTO_INDEX_PLAN_IMMEDIATE,
            bootstrap_plan="immediate",
            readiness_mode="full_target",
        )

    return IngestPolicyDecision(
        size_tier="large",
        auto_index_plan=AUTO_INDEX_PLAN_DEFERRED,
        bootstrap_plan="defer_until_index",
        readiness_mode="degraded_target",
    )
