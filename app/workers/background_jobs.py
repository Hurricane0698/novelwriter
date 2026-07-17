from __future__ import annotations

import logging
import threading
import time

from app.config import get_settings
from app.core.ingest import (
    enqueue_next_deferred_window_index_build,
    run_next_novel_ingest_job,
)
from app.core.indexing.lifecycle import run_next_window_index_rebuild_job
from app.core.world.bootstrap_application import run_next_bootstrap_job
from app.database import SessionLocal, init_db
from app.logging_setup import configure_logging

logger = logging.getLogger(__name__)


def run_worker_loop(
    *,
    once: bool = False,
    stop_event: threading.Event | None = None,
) -> int:
    settings = get_settings()
    configure_logging(is_production=settings.is_production)
    init_db()
    logger.info("background_jobs: worker started")

    idle_cycles = 0
    while True:
        if stop_event is not None and stop_event.is_set():
            break

        did_work = False
        did_work = (
            run_next_novel_ingest_job(session_factory=SessionLocal, settings=settings)
            or did_work
        )
        if stop_event is not None and stop_event.is_set():
            break
        if not did_work:
            did_work = (
                enqueue_next_deferred_window_index_build(
                    session_factory=SessionLocal,
                    settings=settings,
                )
                or did_work
            )
        if stop_event is not None and stop_event.is_set():
            break
        did_work = (
            run_next_window_index_rebuild_job(
                session_factory=SessionLocal, settings=settings
            )
            or did_work
        )
        if stop_event is not None and stop_event.is_set():
            break
        did_work = (
            run_next_bootstrap_job(session_factory=SessionLocal, settings=settings)
            or did_work
        )

        if once:
            return 0

        if did_work:
            idle_cycles = 0
            continue

        idle_cycles += 1
        if idle_cycles == 1 or idle_cycles % 30 == 0:
            logger.debug("background_jobs: idle")
        poll_seconds = max(float(settings.hosted_job_worker_poll_seconds or 0.0), 0.25)
        if stop_event is None:
            time.sleep(poll_seconds)
        elif stop_event.wait(poll_seconds):
            break

    logger.info("background_jobs: worker stopped")
    return 0


def main() -> int:
    return run_worker_loop(once=False)


if __name__ == "__main__":
    raise SystemExit(main())
