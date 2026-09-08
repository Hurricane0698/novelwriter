# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Read-only hosted analytics: trusted events, project outcomes, and report views."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
import logging
from typing import Any, Mapping

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.core.events import (
    DERIVED_METRIC_CATALOG,
    EVENT_CATALOG,
    PUBLIC_CLIENT_EVENT_NAMES,
    PUBLIC_PROJECT_EVENT_NAMES,
    TRUSTED_PROJECT_EVENT_NAMES,
    WORLD_MODEL_ACTIVATION_EVENTS,
    _extract_attribution,
    _meta_get,
    _meta_get_str,
    normalize_event_meta,
)
from app.models import Novel, User, UserEvent

logger = logging.getLogger(__name__)
_PROJECT_ATTRIBUTION_KEYS = (
    "channel",
    "invite_batch",
    "entry_path",
    "landing_path",
    "referrer_host",
    "admission_provider",
)


_EVENT_EFFECTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "world_onboarding_view": (
        "world_onboarding_view_count",
        ("world_onboarding_viewed",),
    ),
    "world_onboarding_dismissed": (
        "world_onboarding_dismiss_count",
        ("world_onboarding_dismissed",),
    ),
    "world_generate_open": ("world_generate_open_count", ()),
    "world_generate_submit": (
        "world_generate_submit_count",
        ("world_onboarding_engaged",),
    ),
    "world_generate_failed": ("world_generate_failed_count", ()),
    "worldpack_import_submit": (
        "worldpack_import_submit_count",
        ("world_onboarding_engaged",),
    ),
    "worldpack_import_failed": ("worldpack_import_failed_count", ()),
    "bootstrap_trigger": ("bootstrap_trigger_count", ("world_onboarding_engaged",)),
    "bootstrap_failed": ("bootstrap_failed_count", ()),
    "demo_guide_view": ("demo_guide_view_count", ()),
    "world_model_view": ("world_model_view_count", ("world_model_viewed",)),
    "copilot_open": ("copilot_open_count", ("copilot_opened",)),
    "copilot_run": ("copilot_run_count", ("copilot_ran",)),
}

_SEGMENT_OUTCOMES = {
    "generated_projects": "generation_count",
    "first_value_projects": "first_value_completed",
    "world_onboarding_view_projects": "world_onboarding_viewed",
    "world_onboarding_engaged_projects": "world_onboarding_engaged",
    "world_generate_submit_projects": "world_generate_submit_count",
    "world_generate_success_projects": "world_generate_count",
    "worldpack_import_projects": "worldpack_import_count",
    "bootstrap_trigger_projects": "bootstrap_trigger_count",
    "bootstrap_run_projects": "bootstrap_run_count",
    "demo_guide_completed_projects": "demo_guide_completed",
    "demo_guide_skipped_projects": "demo_guide_skipped",
    "world_model_view_projects": "world_model_viewed",
    "world_model_activated_projects": "world_model_activated",
    "copilot_open_projects": "copilot_opened",
    "copilot_run_projects": "copilot_ran",
    "copilot_apply_projects": "copilot_applied",
}


def _meta_get_int(meta: Mapping[str, Any] | None, key: str) -> int | None:
    value = _meta_get(meta, key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _new_project(event_row: UserEvent) -> dict[str, Any]:
    return {
        "user_id": int(event_row.user_id),
        "novel_id": int(event_row.novel_id),
        "first_seen_at": event_row.created_at,
        "project_start_at": None,
        "project_start_mode": None,
        "project_start_entry_action": None,
        "project_start_source_surface": None,
        "channel": None,
        "invite_batch": None,
        "entry_path": None,
        "landing_path": None,
        "referrer_host": None,
        "admission_provider": None,
        "upload_source_surface": None,
        "first_generation_at": None,
        "first_value_at": None,
        "first_value_completed": False,
        "world_onboarding_viewed": False,
        "world_onboarding_view_count": 0,
        "world_onboarding_dismissed": False,
        "world_onboarding_dismiss_count": 0,
        "world_onboarding_engaged": False,
        "world_generate_open_count": 0,
        "world_generate_submit_count": 0,
        "world_generate_failed_count": 0,
        "worldpack_import_submit_count": 0,
        "worldpack_import_failed_count": 0,
        "bootstrap_trigger_count": 0,
        "bootstrap_failed_count": 0,
        "demo_guide_view_count": 0,
        "demo_guide_step_count": 0,
        "demo_guide_step_chapter_count": 0,
        "demo_guide_step_atlas_count": 0,
        "demo_guide_step_write_count": 0,
        "demo_guide_step_copilot_count": 0,
        "demo_guide_completed": False,
        "demo_guide_completed_at": None,
        "demo_guide_skipped": False,
        "demo_guide_skipped_at": None,
        "world_model_viewed": False,
        "world_model_view_count": 0,
        "world_model_activated": False,
        "bootstrap_run_count": 0,
        "world_generate_count": 0,
        "worldpack_import_count": 0,
        "draft_confirm_count": 0,
        "draft_reject_count": 0,
        "world_edit_count": 0,
        "copilot_opened": False,
        "copilot_open_count": 0,
        "copilot_ran": False,
        "copilot_run_count": 0,
        "copilot_applied": False,
        "copilot_apply_count": 0,
        "generation_count": 0,
        "chapter_save_count": 0,
    }


def _apply_project_event(
    project: dict[str, Any], row: UserEvent, meta: Mapping[str, Any]
) -> None:
    if project["first_seen_at"] is None or row.created_at < project["first_seen_at"]:
        project["first_seen_at"] = row.created_at

    event = row.event
    effect = _EVENT_EFFECTS.get(event)
    if effect is not None:
        counter, flags = effect
        project[counter] += 1
        for flag in flags:
            project[flag] = True
        return

    if event == "project_start":
        if project["project_start_at"] is None:
            project["project_start_at"] = row.created_at
        for field, meta_key in (
            ("project_start_mode", "start_mode"),
            ("project_start_entry_action", "entry_action"),
            ("project_start_source_surface", "source_surface"),
            *((key, key) for key in _PROJECT_ATTRIBUTION_KEYS),
        ):
            project[field] = _meta_get_str(meta, meta_key) or project[field]
    elif event == "novel_upload":
        project["upload_source_surface"] = (
            _meta_get_str(meta, "source_surface") or project["upload_source_surface"]
        )
    elif event == "generation":
        project["generation_count"] += 1
        if project["first_generation_at"] is None:
            project["first_generation_at"] = row.created_at
    elif event == "chapter_save":
        project["chapter_save_count"] += 1
        if (
            project["first_generation_at"] is not None
            and project["first_value_at"] is None
            and row.created_at >= project["first_generation_at"]
        ):
            project["first_value_at"] = row.created_at
            project["first_value_completed"] = True
    elif event == "demo_guide_step_complete":
        project["demo_guide_step_count"] += 1
        step = _meta_get_str(meta, "step")
        if step in {"chapter", "atlas", "write", "copilot"}:
            project[f"demo_guide_step_{step}_count"] += 1
    elif event in {"demo_guide_completed", "demo_guide_skipped"}:
        project[event] = True
        timestamp = f"{event}_at"
        if project[timestamp] is None:
            project[timestamp] = row.created_at
    elif event in WORLD_MODEL_ACTIVATION_EVENTS:
        project["world_model_activated"] = True
        project["world_onboarding_engaged"] = True
        count = (
            max(1, _meta_get_int(meta, "count") or 1)
            if event in {"draft_confirm", "draft_reject"}
            else 1
        )
        project[f"{event}_count"] += count
    elif event == "copilot_apply":
        count = max(
            0,
            _meta_get_int(meta, "success_count")
            or _meta_get_int(meta, "applied_count")
            or 0,
        )
        project["copilot_apply_count"] += count
        if count > 0:
            project["copilot_applied"] = True


def _trusted_rows(db: Session, rows: list[UserEvent]) -> list[UserEvent]:
    trusted_project_keys: set[tuple[int, int]] = {
        (int(owner_id), int(novel_id))
        for novel_id, owner_id in (
            db.query(Novel.id, Novel.owner_id).filter(Novel.owner_id.is_not(None)).all()
        )
        if owner_id is not None
    }
    for event_row in rows:
        if event_row.user_id is None or event_row.novel_id is None:
            continue
        if event_row.event not in TRUSTED_PROJECT_EVENT_NAMES:
            continue
        trusted_project_keys.add((int(event_row.user_id), int(event_row.novel_id)))

    filtered_rows: list[UserEvent] = []
    for event_row in rows:
        if (
            event_row.event in PUBLIC_PROJECT_EVENT_NAMES
            and event_row.user_id is not None
            and event_row.novel_id is not None
            and (int(event_row.user_id), int(event_row.novel_id))
            not in trusted_project_keys
        ):
            logger.warning(
                "Ignoring untrusted public project analytics event %s for user_id=%s novel_id=%s",
                event_row.event,
                event_row.user_id,
                event_row.novel_id,
            )
            continue
        filtered_rows.append(event_row)

    return filtered_rows


def _summarize_events(
    rows: list[UserEvent],
) -> tuple[dict[str, Any], dict[tuple[int, int], dict[str, Any]]]:
    raw_totals: dict[str, int] = defaultdict(int)
    raw_users: dict[str, set[int]] = defaultdict(set)
    raw_anonymous: dict[str, set[str]] = defaultdict(set)
    raw_projects: dict[str, set[tuple[int, int]]] = defaultdict(set)
    user_signup_meta: dict[int, dict[str, str]] = {}
    projects: dict[tuple[int, int], dict[str, Any]] = {}

    for event_row in rows:
        meta = normalize_event_meta(event_row.meta)
        raw_totals[event_row.event] += 1
        if event_row.user_id is not None:
            raw_users[event_row.event].add(int(event_row.user_id))
        anonymous_id = _meta_get_str(meta, "anonymous_id")
        if anonymous_id:
            raw_anonymous[event_row.event].add(anonymous_id)
        if event_row.user_id is not None and event_row.novel_id is not None:
            raw_projects[event_row.event].add(
                (int(event_row.user_id), int(event_row.novel_id))
            )

        if (
            event_row.event == "signup"
            and event_row.user_id is not None
            and event_row.user_id not in user_signup_meta
        ):
            signup_meta = _extract_attribution(meta)
            admission_provider = _meta_get_str(meta, "admission_provider")
            if admission_provider:
                signup_meta["admission_provider"] = admission_provider
            user_signup_meta[int(event_row.user_id)] = signup_meta

        if event_row.user_id is None or event_row.novel_id is None:
            continue

        key = (int(event_row.user_id), int(event_row.novel_id))
        project = projects.get(key)
        if project is None:
            project = _new_project(event_row)
            projects[key] = project
        _apply_project_event(project, event_row, meta)

    for project in projects.values():
        signup_meta = user_signup_meta.get(project["user_id"], {})
        for key_name in (
            "channel",
            "invite_batch",
            "entry_path",
            "landing_path",
            "referrer_host",
            "admission_provider",
        ):
            if not project.get(key_name):
                project[key_name] = signup_meta.get(key_name)
        if project["project_start_at"] is None:
            project["project_start_at"] = project["first_seen_at"]
        if project["project_start_mode"] is None:
            project["project_start_mode"] = "unknown"

    funnel_summary = {
        event_name: {
            "total": raw_totals[event_name],
            "unique_users": len(raw_users[event_name]),
            "unique_anonymous": len(raw_anonymous[event_name]),
            "unique_projects": len(raw_projects[event_name]),
        }
        for event_name in sorted(raw_totals.keys())
    }

    return funnel_summary, projects


def _summarize_segments(projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    segments: dict[tuple[str, ...], dict[str, Any]] = {}
    dimensions = ("channel", "invite_batch", "entry_path", "project_start_mode")
    for project in projects:
        key = tuple(str(project.get(name) or "unknown") for name in dimensions)
        segment = segments.get(key)
        if segment is None:
            segment = {
                **dict(zip(dimensions, key)),
                "projects": 0,
                **dict.fromkeys(_SEGMENT_OUTCOMES, 0),
            }
            segments[key] = segment
        segment["projects"] += 1
        for metric, field in _SEGMENT_OUTCOMES.items():
            segment[metric] += int(bool(project[field]))
    return [segments[key] for key in sorted(segments)]


def _derive_metrics(
    project_rows: list[dict[str, Any]], filtered_rows: list[UserEvent]
) -> tuple[dict[str, Any], dict[str, Any]]:
    demo_guide_completed_at_by_user: dict[int, datetime] = {}
    for project in project_rows:
        completed_at = project["demo_guide_completed_at"]
        if not isinstance(completed_at, datetime):
            continue
        user_id = int(project["user_id"])
        previous = demo_guide_completed_at_by_user.get(user_id)
        if previous is None or completed_at < previous:
            demo_guide_completed_at_by_user[user_id] = completed_at

    upload_click_after_demo_users: set[int] = set()
    upload_click_after_demo_events = 0
    for event_row in filtered_rows:
        if event_row.event != "upload_cta_click" or event_row.user_id is None:
            continue
        completion_at = demo_guide_completed_at_by_user.get(int(event_row.user_id))
        if completion_at is None or not isinstance(event_row.created_at, datetime):
            continue
        if event_row.created_at >= completion_at:
            upload_click_after_demo_users.add(int(event_row.user_id))
            upload_click_after_demo_events += 1

    uploaded_after_demo_projects = [
        project
        for project in project_rows
        if project["project_start_mode"] == "chapter_import"
        and isinstance(project["project_start_at"], datetime)
        and (
            completion_at := demo_guide_completed_at_by_user.get(
                int(project["user_id"])
            )
        )
        is not None
        and project["project_start_at"] >= completion_at
    ]

    derived_metric_projects = {
        "first_value_completed": [
            project for project in project_rows if project["first_value_completed"]
        ],
        "world_onboarding_engaged": [
            project for project in project_rows if project["world_onboarding_engaged"]
        ],
        "world_model_activated": [
            project for project in project_rows if project["world_model_activated"]
        ],
        "demo_guide_completed": [
            project for project in project_rows if project["demo_guide_completed"]
        ],
        "copilot_discovered": [
            project for project in project_rows if project["copilot_opened"]
        ],
        "copilot_applied": [
            project for project in project_rows if project["copilot_applied"]
        ],
        "uploaded_own_novel_after_demo_guide": uploaded_after_demo_projects,
    }
    derived_metrics = {
        metric_name: {
            "projects": len(project_list),
            "unique_users": len({int(project["user_id"]) for project in project_list}),
            **DERIVED_METRIC_CATALOG[metric_name],
        }
        for metric_name, project_list in derived_metric_projects.items()
    }

    cross_project_user_metrics = {
        "demo_guide_to_upload_click": {
            "users": len(upload_click_after_demo_users),
            "events": upload_click_after_demo_events,
            "description": "Users who clicked any upload CTA after previously completing a guided demo on another project.",
        },
        "demo_guide_to_chapter_import": {
            "users": len(
                {int(project["user_id"]) for project in uploaded_after_demo_projects}
            ),
            "projects": len(uploaded_after_demo_projects),
            "description": "Chapter-import projects started after the same user had already completed a guided demo.",
        },
    }

    return derived_metrics, cross_project_user_metrics


def build_hosted_beta_funnel_report(db: Session) -> dict[str, Any]:
    rows = (
        db.query(UserEvent)
        .order_by(UserEvent.created_at.asc(), UserEvent.id.asc())
        .all()
    )
    total_users = db.query(sa_func.count(User.id)).scalar() or 0

    filtered_rows = _trusted_rows(db, rows)
    funnel_summary, projects = _summarize_events(filtered_rows)

    cutoff = datetime.now() - timedelta(days=30)
    daily_breakdown: dict[str, dict[str, int]] = defaultdict(dict)
    for event_row in filtered_rows:
        created_at = event_row.created_at
        if not isinstance(created_at, datetime) or created_at < cutoff:
            continue
        day = created_at.date().isoformat()
        daily_breakdown[event_row.event][day] = (
            daily_breakdown[event_row.event].get(day, 0) + 1
        )

    project_rows = sorted(
        projects.values(),
        key=lambda item: (
            (item["project_start_at"] or item["first_seen_at"] or datetime.min),
            item["user_id"],
            item["novel_id"],
        ),
    )
    serialized_projects = [
        {
            **{
                k: v
                for k, v in project.items()
                if not k.endswith("_at") and not k.endswith("_seen_at")
            },
            "first_seen_at": _isoformat(project["first_seen_at"]),
            "project_start_at": _isoformat(project["project_start_at"]),
            "first_generation_at": _isoformat(project["first_generation_at"]),
            "first_value_at": _isoformat(project["first_value_at"]),
            "demo_guide_completed_at": _isoformat(project["demo_guide_completed_at"]),
            "demo_guide_skipped_at": _isoformat(project["demo_guide_skipped_at"]),
        }
        for project in project_rows
    ]

    derived_metrics, cross_project_user_metrics = _derive_metrics(
        project_rows, filtered_rows
    )

    recent_events = [
        {
            "user_id": event_row.user_id,
            "anonymous_id": _meta_get_str(
                normalize_event_meta(event_row.meta), "anonymous_id"
            ),
            "event": event_row.event,
            "novel_id": event_row.novel_id,
            "meta": normalize_event_meta(event_row.meta),
            "created_at": _isoformat(event_row.created_at),
        }
        for event_row in filtered_rows[-100:]
    ]

    return {
        "analysis_prompt": (
            "You are analyzing the hosted NovWr writer beta funnel. "
            "The primary success metric is the derived metric first_value_completed, computed from a generation "
            "followed by a later chapter_save on the same project. "
            "Use raw funnel_summary for touchpoints, derived_metrics for project outcomes, cross_project_user_metrics "
            "for demo-to-upload movement, segment_summary for channel/invite-batch/start-mode comparisons, and "
            "project_funnel_rows when you need row-level reasoning. World-model and Copilot signals are secondary "
            "depth metrics and must not replace the core first-value metric."
        ),
        "event_catalog": EVENT_CATALOG,
        "derived_metric_catalog": DERIVED_METRIC_CATALOG,
        "public_event_names": sorted(PUBLIC_CLIENT_EVENT_NAMES),
        "total_users": total_users,
        "funnel_summary": funnel_summary,
        "daily_breakdown_last_30d": dict(daily_breakdown),
        "derived_metrics": derived_metrics,
        "cross_project_user_metrics": cross_project_user_metrics,
        "segment_summary": _summarize_segments(serialized_projects),
        "project_funnel_rows": serialized_projects,
        "recent_events": recent_events,
    }
