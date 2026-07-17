from __future__ import annotations

import threading
from types import SimpleNamespace

from app.workers import background_jobs


def _configure_worker(monkeypatch):
    monkeypatch.setattr(
        background_jobs,
        "get_settings",
        lambda: SimpleNamespace(
            hosted_job_worker_poll_seconds=0.25,
            is_production=False,
        ),
    )
    monkeypatch.setattr(background_jobs, "configure_logging", lambda **_kwargs: None)
    monkeypatch.setattr(background_jobs, "init_db", lambda: None)


def test_worker_stops_before_claiming_when_shutdown_is_already_requested(monkeypatch):
    _configure_worker(monkeypatch)
    stop_event = threading.Event()
    stop_event.set()

    def unexpected_claim(**_kwargs):
        raise AssertionError("worker claimed work after shutdown")

    monkeypatch.setattr(background_jobs, "run_next_novel_ingest_job", unexpected_claim)

    assert background_jobs.run_worker_loop(stop_event=stop_event) == 0


def test_worker_finishes_current_job_without_claiming_another_after_shutdown(
    monkeypatch,
):
    _configure_worker(monkeypatch)
    stop_event = threading.Event()
    calls: list[str] = []

    def finish_ingest(**_kwargs):
        calls.append("ingest")
        stop_event.set()
        return True

    def unexpected_claim(**_kwargs):
        raise AssertionError("worker claimed another job after shutdown")

    monkeypatch.setattr(background_jobs, "run_next_novel_ingest_job", finish_ingest)
    monkeypatch.setattr(
        background_jobs,
        "enqueue_next_deferred_window_index_build",
        unexpected_claim,
    )
    monkeypatch.setattr(
        background_jobs,
        "run_next_window_index_rebuild_job",
        unexpected_claim,
    )
    monkeypatch.setattr(background_jobs, "run_next_bootstrap_job", unexpected_claim)

    assert background_jobs.run_worker_loop(stop_event=stop_event) == 0
    assert calls == ["ingest"]
