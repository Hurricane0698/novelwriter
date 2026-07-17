from __future__ import annotations

AUTO_INDEX_PLAN_IMMEDIATE = "immediate"
AUTO_INDEX_PLAN_DEFERRED = "deferred"
AUTO_INDEX_PLAN_SKIP_AUTO = "skip_auto"


def should_enqueue_window_index_build_immediately(auto_index_plan: str | None) -> bool:
    return auto_index_plan == AUTO_INDEX_PLAN_IMMEDIATE
