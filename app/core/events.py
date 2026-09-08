# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Product analytics event catalog, validation, and recording.

Single entry point for all event tracking. Gated by ENABLE_EVENT_TRACKING config.
Selfhost: off by default. Hosted: enabled via env var.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Mapping

from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.models import UserEvent

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
        "description": "User uploaded a .txt or .md novel for background ingest.",
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
