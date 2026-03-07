# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Hosted safety fuses for signup capacity and AI spend guardrails."""

from __future__ import annotations

from contextlib import contextmanager
import logging
import os

from fastapi import Depends, HTTPException
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db, SessionLocal
from app.models import TokenUsage, User

logger = logging.getLogger(__name__)

_HOSTED_SIGNUP_LOCK_KEY = 0x4E4F5657
_BILLING_SOURCE_HOSTED = "hosted"


def _detail(code: str, message: str, **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {"code": code, "message": message}
    payload.update(extra)
    return payload


def ensure_hosted_user_capacity(db: Session) -> None:
    """Block creation of new hosted users once the configured cap is reached.

    When used as a hard admission gate for user creation, call this inside
    ``hosted_signup_lock()`` so the count check and insert stay atomic.
    """
    settings = get_settings()
    if settings.deploy_mode != "hosted":
        return

    cap = int(settings.hosted_max_users or 0)
    if cap <= 0:
        return

    active_users = (
        db.query(func.count(User.id))
        .filter(User.is_active.is_(True))
        .scalar()
        or 0
    )
    if int(active_users) >= cap:
        raise HTTPException(
            status_code=503,
            detail=_detail(
                "hosted_user_cap_reached",
                "Hosted signup is temporarily closed because the active user cap has been reached.",
                hosted_max_users=cap,
            ),
            headers={"Retry-After": "3600"},
        )


@contextmanager
def hosted_signup_lock(db: Session):
    """Serialize hosted invite signups across processes and threads.

    SQLite uses ``BEGIN IMMEDIATE`` to acquire the database write lock before
    counting active users. PostgreSQL uses a transaction-scoped advisory lock.
    """
    settings = get_settings()
    if settings.deploy_mode != "hosted" or int(settings.hosted_max_users or 0) <= 0:
        yield
        return

    bind = db.get_bind()
    dialect = bind.dialect.name if bind is not None else ""

    if dialect == "sqlite":
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    elif dialect == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": _HOSTED_SIGNUP_LOCK_KEY},
        )
    else:
        logger.warning("Hosted signup lock missing dialect support", extra={"dialect": dialect})

    yield


def get_total_estimated_ai_spend_usd(db: Session) -> float:
    total = (
        db.query(func.coalesce(func.sum(TokenUsage.cost_estimate), 0.0))
        .filter(TokenUsage.billing_source == _BILLING_SOURCE_HOSTED)
        .scalar()
    )
    try:
        return float(total or 0.0)
    except (TypeError, ValueError):
        return 0.0


def get_ai_unavailable_detail(db: Session) -> dict[str, object] | None:
    settings = get_settings()

    if settings.deploy_mode != "hosted":
        return None

    if settings.ai_manual_disable:
        return _detail(
            "ai_manually_disabled",
            "AI features are temporarily disabled by the server operator.",
        )

    hard_stop_usd = float(settings.ai_hard_stop_usd or 0.0)
    if hard_stop_usd <= 0:
        return None

    if os.getenv("DISABLE_TOKEN_USAGE_RECORDING", "").lower() in {"1", "true", "yes", "on"}:
        return _detail(
            "ai_budget_meter_disabled",
            "AI features are temporarily disabled because spend metering is disabled.",
        )

    try:
        total_estimated_usd = get_total_estimated_ai_spend_usd(db)
    except Exception:
        logger.warning("AI spend meter unavailable; failing closed", exc_info=True)
        return _detail(
            "ai_budget_meter_unavailable",
            "AI features are temporarily disabled because the spend meter is unavailable.",
        )

    if total_estimated_usd < hard_stop_usd:
        return None

    return _detail(
        "ai_budget_hard_stop",
        "AI features are temporarily disabled because the estimated hosted AI spend limit has been reached.",
        estimated_total_usd=round(total_estimated_usd, 6),
        hard_stop_usd=round(hard_stop_usd, 6),
    )


def ensure_ai_available(db: Session) -> None:
    detail = get_ai_unavailable_detail(db)
    if detail is None:
        return
    raise HTTPException(
        status_code=503,
        detail=detail,
        headers={"Retry-After": "300"},
    )


def check_ai_available(db: Session = Depends(get_db)) -> None:
    ensure_ai_available(db)


def ensure_ai_available_fresh_session() -> None:
    """Out-of-band guard for background tasks and shared AI clients."""
    db = SessionLocal()
    try:
        ensure_ai_available(db)
    finally:
        db.close()
