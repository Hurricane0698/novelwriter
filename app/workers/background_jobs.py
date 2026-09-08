from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor
import threading
import time

from app.config import Settings, get_settings
from app.core.ingest import (
    enqueue_next_deferred_window_index_build,
    run_next_novel_ingest_job,
)
from app.core.indexing.lifecycle import run_next_window_index_rebuild_job
from app.core.world.bootstrap_application import (
    execute_bootstrap_worker_job,
    prepare_next_bootstrap_job,
    run_next_bootstrap_job,
)
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

    # One CPU lane and one model lane. A waiting provider must not hold up
    # imports/indexes for other novels, and both lanes remain bounded to one job.
    with ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="bootstrap-worker"
    ) as pool:
        _run_worker_cycles(
            settings=settings, once=once, stop_event=stop_event, pool=pool
        )

    logger.info("background_jobs: worker stopped")
    return 0


def _run_worker_cycles(
    *,
    settings: Settings,
    once: bool,
    stop_event: threading.Event | None,
    pool: ThreadPoolExecutor,
) -> None:
    idle_cycles = 0
    bootstrap_future: Future[None] | None = None
    bootstrap_novel_id: int | None = None
    worker_failed = False
    try:
        while True:
            if stop_event is not None and stop_event.is_set():
                break

            if bootstrap_future is not None and bootstrap_future.done():
                finished = bootstrap_future
                bootstrap_future = None
                bootstrap_novel_id = None
                finished.result()

            # Reserve this novel until the runner has finished persistence and closed
            # its session, including time spent waiting for provider concurrency.
            excluded = () if bootstrap_novel_id is None else (bootstrap_novel_id,)

            did_work = False
            did_work = (
                run_next_novel_ingest_job(
                    session_factory=SessionLocal,
                    settings=settings,
                    excluded_novel_ids=excluded,
                )
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
                    session_factory=SessionLocal,
                    settings=settings,
                    excluded_novel_ids=excluded,
                )
                or did_work
            )
            if stop_event is not None and stop_event.is_set():
                break
            if once:
                run_next_bootstrap_job(session_factory=SessionLocal, settings=settings)
                return

            if bootstrap_future is None:
                prepared = prepare_next_bootstrap_job(
                    session_factory=SessionLocal, settings=settings
                )
                if prepared is not None:
                    bootstrap_novel_id = prepared.candidate.novel_id
                    bootstrap_future = pool.submit(
                        execute_bootstrap_worker_job,
                        prepared,
                        session_factory=SessionLocal,
                    )
                    did_work = True

            if did_work:
                idle_cycles = 0
                continue

            idle_cycles += 1
            if idle_cycles == 1 or idle_cycles % 30 == 0:
                logger.debug("background_jobs: idle")
            poll_seconds = max(
                float(settings.hosted_job_worker_poll_seconds or 0.0), 0.25
            )
            if stop_event is None:
                time.sleep(poll_seconds)
            elif stop_event.wait(poll_seconds):
                break

    except BaseException:
        worker_failed = True
        raise
    finally:
        # Finish a selected job even when the CPU lane fails. Preserve the
        # primary failure while reporting a concurrent model failure as well.
        if bootstrap_future is not None:
            if worker_failed:
                try:
                    bootstrap_future.result()
                except BaseException:
                    logger.exception(
                        "background_jobs: bootstrap also failed while worker was stopping"
                    )
            else:
                bootstrap_future.result()


def main() -> int:
    return run_worker_loop(once=False)


if __name__ == "__main__":
    raise SystemExit(main())
