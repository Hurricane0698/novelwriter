# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Lightweight product analytics event recording.

Single entry point for all event tracking. Gated by ENABLE_EVENT_TRACKING config.
Selfhost: off by default. Hosted: enabled via env var.
"""

import logging
from typing import Any

from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import UserEvent

logger = logging.getLogger(__name__)


def record_event(
    db: Session,
    user_id: int,
    event: str,
    novel_id: int | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    """Record a user event if tracking is enabled. Never raises."""
    if not get_settings().enable_event_tracking:
        return
    try:
        # Transaction-neutral: never commit or rollback the caller's session.
        #
        # Use an independent session bound to the same engine so:
        # - we don't accidentally commit unrelated work in the caller's transaction
        # - events can still be persisted even if the caller later rolls back
        bind = db.get_bind()
        engine = getattr(bind, "engine", bind)
        EventSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

        event_db = EventSessionLocal()
        try:
            event_db.add(UserEvent(user_id=user_id, event=event, novel_id=novel_id, meta=meta))
            event_db.commit()
        finally:
            event_db.close()
    except Exception:
        logger.debug("Failed to record event %s for user %s", event, user_id, exc_info=True)
