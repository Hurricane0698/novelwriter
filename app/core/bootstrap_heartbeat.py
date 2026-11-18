# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app.core.bootstrap_contract import is_running_status
from app.models import BootstrapJob

logger = logging.getLogger(__name__)


def resolve_bootstrap_heartbeat_interval_seconds(*, stale_timeout_seconds: int) -> float:
    if stale_timeout_seconds <= 0:
        return 0.0
    return max(min(stale_timeout_seconds / 3, 30.0), 1.0)


def start_bootstrap_job_heartbeat(
    *,
    job_id: int,
    session_factory: Callable[[], Session],
    stale_timeout_seconds: int,
) -> tuple[threading.Event, threading.Thread] | None:
    interval_seconds = resolve_bootstrap_heartbeat_interval_seconds(
        stale_timeout_seconds=stale_timeout_seconds,
    )
    if interval_seconds <= 0:
        return None

    stop_event = threading.Event()

    def _run() -> None:
        while not stop_event.wait(interval_seconds):
            heartbeat_db = session_factory()
            try:
                job = heartbeat_db.query(BootstrapJob).filter(BootstrapJob.id == job_id).first()
                if job is None or not is_running_status(job.status):
                    return
                job.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                heartbeat_db.commit()
            except Exception:
                heartbeat_db.rollback()
                logger.warning(
                    "bootstrap[%d]: failed to refresh heartbeat",
                    job_id,
                    exc_info=True,
                )
            finally:
                heartbeat_db.close()

    thread = threading.Thread(
        target=_run,
        name=f"bootstrap-heartbeat-{job_id}",
        daemon=True,
    )
    thread.start()
    return stop_event, thread


__all__ = [
    "resolve_bootstrap_heartbeat_interval_seconds",
    "start_bootstrap_job_heartbeat",
]
