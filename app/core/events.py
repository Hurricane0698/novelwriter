# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Lightweight product analytics event recording and hosted beta funnel reporting.

Single entry point for all event tracking. Gated by ENABLE_EVENT_TRACKING config.
Selfhost: off by default. Hosted: enabled via env var.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
import logging
import math
from typing import Any, Mapping

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.models import Novel, User, UserEvent

logger = logging.getLogger(__name__)

ANALYTICS_VALUE = str | int | float | bool | None
ATTRIBUTION_META_KEYS: tuple[str, ...] = (
    "anonymous_id",
    "channel",
    "invite_batch",
    "entry_path",
    "landing_path",
    "redirect_to",
    "referrer_host",
    "utm_source",
    "utm_medium",
    "utm_campaign",
)
PUBLIC_CLIENT_EVENT_NAMES = frozenset(
    {
        "acquisition_landing_view",
        "acquisition_cta_click",
        "invite_gate_view",
        "invite_gate_submit",
        "upload_cta_click",
        "world_onboarding_view",
        "world_onboarding_dismissed",
        "world_generate_open",
        "world_generate_submit",
        "world_generate_failed",
        "worldpack_import_submit",
        "worldpack_import_failed",
        "bootstrap_trigger",
        "bootstrap_failed",
        "demo_guide_view",
        "demo_guide_step_complete",
        "demo_guide_completed",
        "demo_guide_skipped",
        "world_model_view",
        "copilot_open",
    }
)
PUBLIC_PROJECT_EVENT_NAMES = frozenset(
    {
        "world_onboarding_view",
        "world_onboarding_dismissed",
        "world_generate_open",
        "world_generate_submit",
        "world_generate_failed",
        "worldpack_import_submit",
        "worldpack_import_failed",
        "bootstrap_trigger",
        "bootstrap_failed",
        "demo_guide_view",
        "demo_guide_step_complete",
        "demo_guide_completed",
        "demo_guide_skipped",
        "world_model_view",
        "copilot_open",
    }
)
PUBLIC_NON_PROJECT_EVENT_NAMES = PUBLIC_CLIENT_EVENT_NAMES - PUBLIC_PROJECT_EVENT_NAMES
PROJECT_START_MODES = frozenset({"demo", "setting_import", "chapter_import"})
WORLD_MODEL_ACTIVATION_EVENTS = frozenset(
    {
        "bootstrap_run",
        "world_generate",
        "worldpack_import",
        "draft_confirm",
        "draft_reject",
        "world_edit",
    }
)
TRUSTED_PROJECT_EVENT_NAMES = frozenset(
    {
        "project_start",
        "novel_upload",
        "bootstrap_run",
        "world_generate",
        "worldpack_import",
        "draft_confirm",
        "draft_reject",
        "world_edit",
        "copilot_run",
        "copilot_apply",
        "generation",
        "chapter_save",
    }
)

EVENT_CATALOG: dict[str, dict[str, Any]] = {
    "acquisition_landing_view": {
        "description": "Anonymous visitor viewed the hosted writer-beta landing/acquisition surface.",
        "funnel_position": 0,
        "question": "How much qualified traffic reaches the hosted writer-beta entry surface?",
        "meta_keys": {
            "channel": "distribution channel / acquisition source",
            "invite_batch": "invite cohort or outreach batch",
            "entry_path": "first captured public entry path",
            "anonymous_id": "anonymous browser-scoped attribution id",
        },
    },
    "acquisition_cta_click": {
        "description": "Anonymous visitor clicked a primary acquisition CTA toward hosted login.",
        "funnel_position": 0,
        "question": "Which public entry surfaces generate real login intent?",
        "meta_keys": {
            "cta": "hero|footer|navbar|other",
            "destination": "target path, usually /login",
            "channel": "distribution channel / acquisition source",
            "invite_batch": "invite cohort or outreach batch",
            "entry_path": "first captured public entry path",
            "anonymous_id": "anonymous browser-scoped attribution id",
        },
    },
    "invite_gate_view": {
        "description": "Visitor reached the hosted invite gate / login surface.",
        "funnel_position": 1,
        "question": "How many visitors make it from acquisition to the invite gate?",
        "meta_keys": {
            "channel": "distribution channel / acquisition source",
            "invite_batch": "invite cohort or outreach batch",
            "entry_path": "first captured public entry path",
            "anonymous_id": "anonymous browser-scoped attribution id",
        },
    },
    "invite_gate_submit": {
        "description": "Visitor submitted the invite gate form.",
        "funnel_position": 2,
        "question": "Where does the invite gate itself create drop-off?",
        "meta_keys": {
            "method": "invite",
            "channel": "distribution channel / acquisition source",
            "invite_batch": "invite cohort or outreach batch",
            "entry_path": "first captured public entry path",
            "anonymous_id": "anonymous browser-scoped attribution id",
        },
    },
    "upload_cta_click": {
        "description": "Authenticated user clicked an upload CTA before selecting a manuscript file.",
        "funnel_position": 4,
        "question": "Which authenticated surfaces lead users toward importing their own manuscript?",
        "meta_keys": {
            "source_surface": "library_header|library_empty_state|library_demo_card|other",
        },
    },
    "signup": {
        "description": "Hosted user admitted into the beta through a provider-backed signup/login path.",
        "funnel_position": 3,
        "question": "How many invite-gated visitors become real beta accounts?",
        "meta_keys": {
            "admission_provider": "invite|github",
            "channel": "distribution channel / acquisition source",
            "invite_batch": "invite cohort or outreach batch",
            "entry_path": "first captured public entry path",
            "anonymous_id": "anonymous browser-scoped attribution id if captured pre-signup",
        },
    },
    "project_start": {
        "description": "User actually chose a project start mode for the hosted writer workflow.",
        "funnel_position": 4,
        "question": "Do users start from the guided demo, settings-first world build, or chapter import?",
        "meta_keys": {
            "start_mode": "demo|setting_import|chapter_import",
            "entry_action": "demo_open|novel_upload|world_generate|worldpack_import",
            "source_surface": "UI surface that started the project when known",
            "channel": "distribution channel / acquisition source",
            "invite_batch": "invite cohort or outreach batch",
            "entry_path": "first captured public entry path",
        },
    },
    "novel_upload": {
        "description": "User uploaded a novel (.txt file accepted for background ingest).",
        "funnel_position": 4,
        "question": "How many started a chapter-import project?",
        "meta_keys": {
            "bytes_uploaded": "uploaded file size in bytes",
            "consent_acknowledged": "whether the upload consent gate was confirmed",
            "consent_version": "accepted upload consent version",
            "language": "upload language persisted at accept time",
            "upload_duration_ms": "server-side upload accept/write duration",
            "source_surface": "library_header|library_empty_state|library_demo_card|other",
        },
    },
    "world_onboarding_view": {
        "description": "User saw the empty-world onboarding gate with the setting-generation and chapter-extraction options.",
        "funnel_position": 5,
        "question": "How many eligible projects actually reach the world-building choice point?",
        "meta_keys": {
            "surface": "studio",
        },
    },
    "world_onboarding_dismissed": {
        "description": "User dismissed the empty-world onboarding gate without starting a world-building action there.",
        "funnel_position": 5,
        "question": "How often do users defer world-building instead of picking one of the onboarding actions?",
        "meta_keys": {
            "surface": "studio",
        },
    },
    "world_generate_open": {
        "description": "User opened the settings-to-world generation dialog.",
        "funnel_position": 5,
        "question": "How many users enter the setting-import generation flow before submitting text?",
        "meta_keys": {
            "source_surface": "world_onboarding|copilot_card|unknown",
        },
    },
    "world_generate_submit": {
        "description": "User submitted setting text for world generation.",
        "funnel_position": 5,
        "question": "How often do users actually attempt the setting-import generation flow?",
        "meta_keys": {
            "source_surface": "world_onboarding|copilot_card|unknown",
            "text_length": "submitted character count after trim",
        },
    },
    "world_generate_failed": {
        "description": "The settings-to-world generation flow failed after the user submitted it.",
        "funnel_position": 5,
        "question": "Where does the setting-import path fail before it becomes successful world-model output?",
        "meta_keys": {
            "source_surface": "world_onboarding|copilot_card|unknown",
            "status": "HTTP status when available",
            "error_code": "stable frontend/backend error code when available",
        },
    },
    "worldpack_import_submit": {
        "description": "User submitted a worldpack import from the settings-generation dialog.",
        "funnel_position": 5,
        "question": "How often do users choose worldpack import instead of free-text generation?",
        "meta_keys": {
            "source_surface": "world_onboarding|copilot_card|unknown",
        },
    },
    "worldpack_import_failed": {
        "description": "The worldpack import flow failed after the user selected a file.",
        "funnel_position": 5,
        "question": "Where does worldpack import break before it creates usable world-model data?",
        "meta_keys": {
            "source_surface": "world_onboarding|copilot_card|unknown",
            "error_code": "stable frontend/backend error code when available",
        },
    },
    "bootstrap_run": {
        "description": "Bootstrap pipeline completed (chapter extraction into world-model drafts).",
        "funnel_position": 5,
        "question": "Do users run chapter-based world-model extraction after getting into a project?",
        "meta_keys": {
            "mode": "bootstrap mode (initial/reextract/index_refresh)",
            "entities_found": "int",
            "relationships_found": "int",
        },
    },
    "bootstrap_trigger": {
        "description": "User explicitly started chapter extraction / bootstrap from the UI.",
        "funnel_position": 5,
        "question": "How often do users choose chapter extraction before it either succeeds or fails?",
        "meta_keys": {
            "mode": "initial|reextract|index_refresh",
            "source_surface": "world_onboarding|copilot_card|unknown",
        },
    },
    "bootstrap_failed": {
        "description": "The bootstrap trigger failed before a successful background completion event was recorded.",
        "funnel_position": 5,
        "question": "Where does chapter extraction fail before it produces world-model drafts?",
        "meta_keys": {
            "mode": "initial|reextract|index_refresh",
            "source_surface": "world_onboarding|copilot_card|unknown",
            "status": "HTTP status when available",
            "error_code": "stable frontend/backend error code when available",
        },
    },
    "demo_guide_view": {
        "description": "User saw the in-Studio guided demo card/checklist.",
        "funnel_position": 5,
        "question": "How many demo projects expose the guided sample checklist to the user?",
        "meta_keys": {
            "source": "auto|reopen",
            "status": "not_started|in_progress|completed|skipped",
            "progress_count": "number of completed checklist steps",
        },
    },
    "demo_guide_step_complete": {
        "description": "User completed one step in the guided demo checklist.",
        "funnel_position": 5,
        "question": "Which guided-demo steps are users actually completing?",
        "meta_keys": {
            "step": "chapter|atlas|write|copilot",
            "progress_count": "number of completed checklist steps after this event",
        },
    },
    "demo_guide_completed": {
        "description": "User completed the guided demo checklist for a demo novel.",
        "funnel_position": 5,
        "question": "How many demo projects actually reach guided-demo completion?",
    },
    "demo_guide_skipped": {
        "description": "User explicitly skipped the guided demo checklist.",
        "funnel_position": 5,
        "question": "How often do users choose to skip the demo checklist instead of completing it?",
        "meta_keys": {
            "progress_count": "number of completed checklist steps when the guide was skipped",
        },
    },
    "world_model_view": {
        "description": "User opened the world-model workspace / Atlas surface.",
        "funnel_position": 5,
        "question": "Do users discover the world model at all before deeper usage?",
        "meta_keys": {
            "surface": "atlas",
            "tab": "current atlas tab when opened",
        },
    },
    "draft_confirm": {
        "description": "User accepted AI-generated draft entities/relationships/systems into their world model.",
        "funnel_position": 6,
        "question": "Adoption rate: what fraction of AI-generated world-model drafts do users keep?",
        "meta_keys": {"type": "entity|relationship|system", "count": "number confirmed in this batch"},
    },
    "draft_reject": {
        "description": "User rejected AI-generated world-model drafts.",
        "funnel_position": 6,
        "question": "Rejection rate: where is world-model output still weak or confusing?",
        "meta_keys": {"type": "entity|relationship|system", "count": "number rejected in this batch"},
    },
    "world_generate": {
        "description": "User generated world-model drafts from pasted setting text.",
        "funnel_position": 6,
        "question": "Do users prefer setting-import world building over chapter-import extraction?",
    },
    "worldpack_import": {
        "description": "User successfully imported a worldpack into the world model.",
        "funnel_position": 6,
        "question": "How often does the worldpack branch produce successful world-model starts?",
        "meta_keys": {
            "pack_id": "worldpack identifier",
            "warnings_count": "number of import warnings",
            "entities_created": "created entity rows",
            "relationships_created": "created relationship rows",
            "systems_created": "created system rows",
        },
    },
    "world_edit": {
        "description": "User manually created or edited a world-model element.",
        "funnel_position": 6,
        "question": "Do users engage with the world model deeply enough to edit it manually?",
        "meta_keys": {"action": "create_entity|update_entity|create_relationship|update_relationship|create_system|update_system"},
    },
    "copilot_open": {
        "description": "User opened Novel Copilot from a concrete surface.",
        "funnel_position": 6,
        "question": "Do users notice and try Copilot as a secondary depth signal?",
        "meta_keys": {
            "surface": "studio|atlas|standalone|unknown",
            "mode": "whole_book|entity|draft_review|relationships|...",
            "scope": "whole_book|entity|draft_review|relationships|...",
        },
    },
    "copilot_run": {
        "description": "User launched a Copilot research run.",
        "funnel_position": 6,
        "question": "Does Copilot progress from discovery to actual usage?",
        "meta_keys": {
            "mode": "copilot session mode",
            "scope": "copilot session scope",
            "quick_action_id": "preset quick action id when present",
            "is_resume": "true when retrying an interrupted run",
        },
    },
    "copilot_apply": {
        "description": "User applied Copilot suggestions back into the world model.",
        "funnel_position": 6,
        "question": "Does Copilot produce suggestions that users trust enough to apply?",
        "meta_keys": {
            "requested_count": "number of suggestions selected for apply",
            "success_count": "number of suggestions applied successfully",
            "mode": "copilot session mode",
            "scope": "copilot session scope",
        },
    },
    "generation": {
        "description": "Novel continuation generated successfully (the core value-delivery moment).",
        "funnel_position": 7,
        "question": "Core loop: are users actually generating text?",
        "meta_keys": {
            "variants": "number of variants generated",
            "stream": "true if via streaming endpoint",
            "delivery_mode": "sync|stream|stream_fallback",
        },
    },
    "chapter_save": {
        "description": "User saved/updated a chapter (may incorporate generated content).",
        "funnel_position": 8,
        "question": "Retention/value signal: are users integrating generated output into their work?",
        "meta_keys": {"chapter": "chapter number"},
    },
}


DERIVED_METRIC_CATALOG: dict[str, dict[str, str]] = {
    "first_value_completed": {
        "description": "Derived per project from generation followed by a later chapter_save on the same novel.",
        "question": "How many projects actually reach the hosted writer beta's first value moment?",
    },
    "world_onboarding_engaged": {
        "description": "Derived per project from any empty-world choice entering generation, extraction, or worldpack import.",
        "question": "How many projects move beyond seeing the world onboarding and actually choose a world-building path?",
    },
    "world_model_activated": {
        "description": "Derived per project from bootstrap/world_generate/worldpack import/draft review/world_edit events.",
        "question": "How many projects go beyond merely seeing the world model and actually use it?",
    },
    "demo_guide_completed": {
        "description": "Derived per project from a guided demo checklist completion.",
        "question": "How many demo projects actually complete the guided sample instead of just opening it?",
    },
    "copilot_discovered": {
        "description": "Derived per project from copilot_open.",
        "question": "How many projects discover Copilot at all?",
    },
    "copilot_applied": {
        "description": "Derived per project from copilot_apply success_count > 0.",
        "question": "How many projects trust Copilot enough to apply suggestions?",
    },
    "uploaded_own_novel_after_demo_guide": {
        "description": "Derived per chapter-import project when the same user previously completed a demo guide on another project.",
        "question": "After completing the guided demo, how many users go on to upload their own manuscript?",
    },
}


def public_event_requires_novel_id(event_name: str) -> bool:
    return event_name in PUBLIC_PROJECT_EVENT_NAMES


def public_event_forbids_novel_id(event_name: str) -> bool:
    return event_name in PUBLIC_NON_PROJECT_EVENT_NAMES


def _normalize_meta_value(value: Any) -> ANALYTICS_VALUE:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        normalized = value.strip()
        return normalized[:240] if normalized else None
    return None


def normalize_event_meta(meta: Mapping[str, Any] | None) -> dict[str, ANALYTICS_VALUE]:
    if not meta:
        return {}
    cleaned: dict[str, ANALYTICS_VALUE] = {}
    for raw_key, raw_value in meta.items():
        if not isinstance(raw_key, str):
            continue
        key = raw_key.strip()[:64]
        if not key:
            continue
        value = _normalize_meta_value(raw_value)
        if value is None and raw_value is not None:
            continue
        cleaned[key] = value
    return cleaned


def _meta_get(meta: Mapping[str, Any] | None, key: str) -> ANALYTICS_VALUE:
    if not meta:
        return None
    return _normalize_meta_value(meta.get(key))


def _meta_get_str(meta: Mapping[str, Any] | None, key: str) -> str | None:
    value = _meta_get(meta, key)
    return value if isinstance(value, str) and value else None


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


def _extract_attribution(meta: Mapping[str, Any] | None) -> dict[str, str]:
    attribution: dict[str, str] = {}
    for key in ATTRIBUTION_META_KEYS:
        value = _meta_get_str(meta, key)
        if value:
            attribution[key] = value
    return attribution


def record_event(
    db: Session,
    user_id: int | None,
    event: str,
    novel_id: int | None = None,
    meta: Mapping[str, Any] | None = None,
    *,
    anonymous_id: str | None = None,
) -> None:
    """Record a product event if tracking is enabled. Never raises."""
    if not get_settings().enable_event_tracking:
        return

    resolved_meta = normalize_event_meta(meta)
    resolved_anonymous_id = (anonymous_id or "").strip()[:64]
    if resolved_anonymous_id:
        resolved_meta.setdefault("anonymous_id", resolved_anonymous_id)

    if user_id is None and not resolved_meta.get("anonymous_id"):
        return

    try:
        # Transaction-neutral: never commit or rollback the caller's session.
        bind = db.get_bind()
        engine = getattr(bind, "engine", bind)
        event_session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)

        event_db = event_session_local()
        try:
            event_db.add(
                UserEvent(
                    user_id=user_id,
                    event=event,
                    novel_id=novel_id,
                    meta=resolved_meta or None,
                )
            )
            event_db.commit()
        finally:
            event_db.close()
    except Exception:
        logger.debug("Failed to record event %s for user %s", event, user_id, exc_info=True)


def resolve_signup_attribution(db: Session, user_id: int) -> dict[str, str]:
    signup_event = (
        db.query(UserEvent)
        .filter(UserEvent.user_id == user_id, UserEvent.event == "signup")
        .order_by(UserEvent.created_at.asc(), UserEvent.id.asc())
        .first()
    )
    if signup_event is None:
        return {}

    meta = normalize_event_meta(signup_event.meta)
    attribution = _extract_attribution(meta)
    admission_provider = _meta_get_str(meta, "admission_provider")
    if admission_provider:
        attribution["admission_provider"] = admission_provider
    return attribution


def ensure_project_start_event(
    db: Session,
    *,
    user_id: int,
    novel_id: int,
    start_mode: str,
    meta: Mapping[str, Any] | None = None,
) -> bool:
    if start_mode not in PROJECT_START_MODES:
        raise ValueError(f"Unsupported project start mode: {start_mode}")

    existing = (
        db.query(UserEvent.id)
        .filter(
            UserEvent.user_id == user_id,
            UserEvent.novel_id == novel_id,
            UserEvent.event == "project_start",
        )
        .first()
    )
    if existing is not None:
        return False

    payload: dict[str, Any] = {"start_mode": start_mode}
    payload.update(resolve_signup_attribution(db, user_id))
    payload.update(normalize_event_meta(meta))
    record_event(db, user_id, "project_start", novel_id=novel_id, meta=payload)
    return True


def build_hosted_beta_funnel_report(db: Session) -> dict[str, Any]:
    rows = (
        db.query(UserEvent)
        .order_by(UserEvent.created_at.asc(), UserEvent.id.asc())
        .all()
    )
    total_users = db.query(sa_func.count(User.id)).scalar() or 0

    trusted_project_keys: set[tuple[int, int]] = {
        (int(owner_id), int(novel_id))
        for novel_id, owner_id in (
            db.query(Novel.id, Novel.owner_id)
            .filter(Novel.owner_id.is_not(None))
            .all()
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
            and (int(event_row.user_id), int(event_row.novel_id)) not in trusted_project_keys
        ):
            logger.warning(
                "Ignoring untrusted public project analytics event %s for user_id=%s novel_id=%s",
                event_row.event,
                event_row.user_id,
                event_row.novel_id,
            )
            continue
        filtered_rows.append(event_row)

    raw_totals: dict[str, int] = defaultdict(int)
    raw_users: dict[str, set[int]] = defaultdict(set)
    raw_anonymous: dict[str, set[str]] = defaultdict(set)
    raw_projects: dict[str, set[tuple[int, int]]] = defaultdict(set)
    user_signup_meta: dict[int, dict[str, str]] = {}
    projects: dict[tuple[int, int], dict[str, Any]] = {}

    for event_row in filtered_rows:
        meta = normalize_event_meta(event_row.meta)
        raw_totals[event_row.event] += 1
        if event_row.user_id is not None:
            raw_users[event_row.event].add(int(event_row.user_id))
        anonymous_id = _meta_get_str(meta, "anonymous_id")
        if anonymous_id:
            raw_anonymous[event_row.event].add(anonymous_id)
        if event_row.user_id is not None and event_row.novel_id is not None:
            raw_projects[event_row.event].add((int(event_row.user_id), int(event_row.novel_id)))

        if event_row.event == "signup" and event_row.user_id is not None and event_row.user_id not in user_signup_meta:
            signup_meta = _extract_attribution(meta)
            admission_provider = _meta_get_str(meta, "admission_provider")
            if admission_provider:
                signup_meta["admission_provider"] = admission_provider
            user_signup_meta[int(event_row.user_id)] = signup_meta

        if event_row.user_id is None or event_row.novel_id is None:
            continue

        key = (int(event_row.user_id), int(event_row.novel_id))
        project = projects.setdefault(
            key,
            {
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
            },
        )
        if project["first_seen_at"] is None or event_row.created_at < project["first_seen_at"]:
            project["first_seen_at"] = event_row.created_at

        if event_row.event == "project_start":
            if project["project_start_at"] is None:
                project["project_start_at"] = event_row.created_at
            project["project_start_mode"] = _meta_get_str(meta, "start_mode") or project["project_start_mode"]
            project["project_start_entry_action"] = _meta_get_str(meta, "entry_action") or project["project_start_entry_action"]
            project["project_start_source_surface"] = _meta_get_str(meta, "source_surface") or project["project_start_source_surface"]
            for key_name in ("channel", "invite_batch", "entry_path", "landing_path", "referrer_host"):
                value = _meta_get_str(meta, key_name)
                if value:
                    project[key_name] = value
            admission_provider = _meta_get_str(meta, "admission_provider")
            if admission_provider:
                project["admission_provider"] = admission_provider
            continue

        if event_row.event == "novel_upload":
            upload_source_surface = _meta_get_str(meta, "source_surface")
            if upload_source_surface:
                project["upload_source_surface"] = upload_source_surface
            continue

        if event_row.event == "generation":
            project["generation_count"] += 1
            if project["first_generation_at"] is None:
                project["first_generation_at"] = event_row.created_at
            continue

        if event_row.event == "chapter_save":
            project["chapter_save_count"] += 1
            if (
                project["first_generation_at"] is not None
                and project["first_value_at"] is None
                and event_row.created_at >= project["first_generation_at"]
            ):
                project["first_value_at"] = event_row.created_at
                project["first_value_completed"] = True
            continue

        if event_row.event == "world_onboarding_view":
            project["world_onboarding_viewed"] = True
            project["world_onboarding_view_count"] += 1
            continue

        if event_row.event == "world_onboarding_dismissed":
            project["world_onboarding_dismissed"] = True
            project["world_onboarding_dismiss_count"] += 1
            continue

        if event_row.event == "world_generate_open":
            project["world_generate_open_count"] += 1
            continue

        if event_row.event == "world_generate_submit":
            project["world_onboarding_engaged"] = True
            project["world_generate_submit_count"] += 1
            continue

        if event_row.event == "world_generate_failed":
            project["world_generate_failed_count"] += 1
            continue

        if event_row.event == "worldpack_import_submit":
            project["world_onboarding_engaged"] = True
            project["worldpack_import_submit_count"] += 1
            continue

        if event_row.event == "worldpack_import_failed":
            project["worldpack_import_failed_count"] += 1
            continue

        if event_row.event == "bootstrap_trigger":
            project["world_onboarding_engaged"] = True
            project["bootstrap_trigger_count"] += 1
            continue

        if event_row.event == "bootstrap_failed":
            project["bootstrap_failed_count"] += 1
            continue

        if event_row.event == "demo_guide_view":
            project["demo_guide_view_count"] += 1
            continue

        if event_row.event == "demo_guide_step_complete":
            project["demo_guide_step_count"] += 1
            step = _meta_get_str(meta, "step")
            if step == "chapter":
                project["demo_guide_step_chapter_count"] += 1
            elif step == "atlas":
                project["demo_guide_step_atlas_count"] += 1
            elif step == "write":
                project["demo_guide_step_write_count"] += 1
            elif step == "copilot":
                project["demo_guide_step_copilot_count"] += 1
            continue

        if event_row.event == "demo_guide_completed":
            project["demo_guide_completed"] = True
            if project["demo_guide_completed_at"] is None:
                project["demo_guide_completed_at"] = event_row.created_at
            continue

        if event_row.event == "demo_guide_skipped":
            project["demo_guide_skipped"] = True
            if project["demo_guide_skipped_at"] is None:
                project["demo_guide_skipped_at"] = event_row.created_at
            continue

        if event_row.event == "world_model_view":
            project["world_model_viewed"] = True
            project["world_model_view_count"] += 1
            continue

        if event_row.event in WORLD_MODEL_ACTIVATION_EVENTS:
            project["world_model_activated"] = True
            project["world_onboarding_engaged"] = True
            if event_row.event == "bootstrap_run":
                project["bootstrap_run_count"] += 1
            elif event_row.event == "world_generate":
                project["world_generate_count"] += 1
            elif event_row.event == "worldpack_import":
                project["worldpack_import_count"] += 1
            elif event_row.event == "draft_confirm":
                project["draft_confirm_count"] += max(1, _meta_get_int(meta, "count") or 1)
            elif event_row.event == "draft_reject":
                project["draft_reject_count"] += max(1, _meta_get_int(meta, "count") or 1)
            elif event_row.event == "world_edit":
                project["world_edit_count"] += 1
            continue

        if event_row.event == "copilot_open":
            project["copilot_opened"] = True
            project["copilot_open_count"] += 1
            continue

        if event_row.event == "copilot_run":
            project["copilot_ran"] = True
            project["copilot_run_count"] += 1
            continue

        if event_row.event == "copilot_apply":
            success_count = max(0, _meta_get_int(meta, "success_count") or _meta_get_int(meta, "applied_count") or 0)
            project["copilot_apply_count"] += success_count
            if success_count > 0:
                project["copilot_applied"] = True
            continue

    for project in projects.values():
        signup_meta = user_signup_meta.get(project["user_id"], {})
        for key_name in ("channel", "invite_batch", "entry_path", "landing_path", "referrer_host", "admission_provider"):
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

    cutoff = datetime.now() - timedelta(days=30)
    daily_breakdown: dict[str, dict[str, int]] = defaultdict(dict)
    for event_row in filtered_rows:
        created_at = event_row.created_at
        if not isinstance(created_at, datetime) or created_at < cutoff:
            continue
        day = created_at.date().isoformat()
        daily_breakdown[event_row.event][day] = daily_breakdown[event_row.event].get(day, 0) + 1

    project_rows = sorted(
        projects.values(),
        key=lambda item: ((item["project_start_at"] or item["first_seen_at"] or datetime.min), item["user_id"], item["novel_id"]),
    )
    serialized_projects = [
        {
            **{k: v for k, v in project.items() if not k.endswith("_at") and not k.endswith("_seen_at")},
            "first_seen_at": _isoformat(project["first_seen_at"]),
            "project_start_at": _isoformat(project["project_start_at"]),
            "first_generation_at": _isoformat(project["first_generation_at"]),
            "first_value_at": _isoformat(project["first_value_at"]),
            "demo_guide_completed_at": _isoformat(project["demo_guide_completed_at"]),
            "demo_guide_skipped_at": _isoformat(project["demo_guide_skipped_at"]),
        }
        for project in project_rows
    ]

    segment_summary: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for project in serialized_projects:
        key = (
            str(project.get("channel") or "unknown"),
            str(project.get("invite_batch") or "unknown"),
            str(project.get("entry_path") or "unknown"),
            str(project.get("project_start_mode") or "unknown"),
        )
        segment = segment_summary.setdefault(
            key,
            {
                "channel": key[0],
                "invite_batch": key[1],
                "entry_path": key[2],
                "project_start_mode": key[3],
                "projects": 0,
                "generated_projects": 0,
                "first_value_projects": 0,
                "world_onboarding_view_projects": 0,
                "world_onboarding_engaged_projects": 0,
                "world_generate_submit_projects": 0,
                "world_generate_success_projects": 0,
                "worldpack_import_projects": 0,
                "bootstrap_trigger_projects": 0,
                "bootstrap_run_projects": 0,
                "demo_guide_completed_projects": 0,
                "demo_guide_skipped_projects": 0,
                "world_model_view_projects": 0,
                "world_model_activated_projects": 0,
                "copilot_open_projects": 0,
                "copilot_run_projects": 0,
                "copilot_apply_projects": 0,
            },
        )
        segment["projects"] += 1
        if project["generation_count"] > 0:
            segment["generated_projects"] += 1
        if project["first_value_completed"]:
            segment["first_value_projects"] += 1
        if project["world_onboarding_viewed"]:
            segment["world_onboarding_view_projects"] += 1
        if project["world_onboarding_engaged"]:
            segment["world_onboarding_engaged_projects"] += 1
        if project["world_generate_submit_count"] > 0:
            segment["world_generate_submit_projects"] += 1
        if project["world_generate_count"] > 0:
            segment["world_generate_success_projects"] += 1
        if project["worldpack_import_count"] > 0:
            segment["worldpack_import_projects"] += 1
        if project["bootstrap_trigger_count"] > 0:
            segment["bootstrap_trigger_projects"] += 1
        if project["bootstrap_run_count"] > 0:
            segment["bootstrap_run_projects"] += 1
        if project["demo_guide_completed"]:
            segment["demo_guide_completed_projects"] += 1
        if project["demo_guide_skipped"]:
            segment["demo_guide_skipped_projects"] += 1
        if project["world_model_viewed"]:
            segment["world_model_view_projects"] += 1
        if project["world_model_activated"]:
            segment["world_model_activated_projects"] += 1
        if project["copilot_opened"]:
            segment["copilot_open_projects"] += 1
        if project["copilot_ran"]:
            segment["copilot_run_projects"] += 1
        if project["copilot_applied"]:
            segment["copilot_apply_projects"] += 1

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
        and (completion_at := demo_guide_completed_at_by_user.get(int(project["user_id"]))) is not None
        and project["project_start_at"] >= completion_at
    ]

    derived_metric_projects = {
        "first_value_completed": [project for project in project_rows if project["first_value_completed"]],
        "world_onboarding_engaged": [project for project in project_rows if project["world_onboarding_engaged"]],
        "world_model_activated": [project for project in project_rows if project["world_model_activated"]],
        "demo_guide_completed": [project for project in project_rows if project["demo_guide_completed"]],
        "copilot_discovered": [project for project in project_rows if project["copilot_opened"]],
        "copilot_applied": [project for project in project_rows if project["copilot_applied"]],
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
            "users": len({int(project["user_id"]) for project in uploaded_after_demo_projects}),
            "projects": len(uploaded_after_demo_projects),
            "description": "Chapter-import projects started after the same user had already completed a guided demo.",
        },
    }

    recent_events = [
        {
            "user_id": event_row.user_id,
            "anonymous_id": _meta_get_str(normalize_event_meta(event_row.meta), "anonymous_id"),
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
        "segment_summary": sorted(segment_summary.values(), key=lambda row: (row["channel"], row["invite_batch"], row["entry_path"], row["project_start_mode"])),
        "project_funnel_rows": serialized_projects,
        "recent_events": recent_events,
    }
