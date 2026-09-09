from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

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


def test_model_wait_allows_other_novels_and_shutdown_drains_current_job(monkeypatch):
    _configure_worker(monkeypatch)
    stop = threading.Event()
    model_started = threading.Event()
    other_novel_processed = threading.Event()
    release_model = threading.Event()
    preparations = []
    exclusions = []

    def prepare(**_kwargs):
        preparations.append(7)
        return SimpleNamespace(candidate=SimpleNamespace(novel_id=7))

    def model_job(_prepared, **_kwargs):
        model_started.set()
        assert release_model.wait(3)

    def ingest(*, excluded_novel_ids, **_kwargs):
        if excluded_novel_ids:
            assert model_started.wait(2)
            exclusions.append(excluded_novel_ids)
            # A queued job for a different novel can finish while LLM is blocked.
            other_novel_processed.set()
            stop.set()
            return True
        return False

    monkeypatch.setattr(background_jobs, "run_next_novel_ingest_job", ingest)
    monkeypatch.setattr(
        background_jobs, "enqueue_next_deferred_window_index_build", lambda **kw: False
    )
    monkeypatch.setattr(
        background_jobs, "run_next_window_index_rebuild_job", lambda **kw: False
    )
    monkeypatch.setattr(background_jobs, "prepare_next_bootstrap_job", prepare)
    monkeypatch.setattr(background_jobs, "execute_bootstrap_worker_job", model_job)
    with ThreadPoolExecutor(max_workers=1) as pool:
        worker = pool.submit(background_jobs.run_worker_loop, stop_event=stop)
        try:
            assert other_novel_processed.wait(2)
            assert not worker.done()
        finally:
            stop.set()
            release_model.set()
        assert worker.result(timeout=2) == 0
    assert exclusions == [(7,)]
    assert preparations == [7]


def test_model_runner_failure_is_observed_when_worker_stops(monkeypatch):
    _configure_worker(monkeypatch)
    stop = threading.Event()
    for name in (
        "run_next_novel_ingest_job",
        "enqueue_next_deferred_window_index_build",
        "run_next_window_index_rebuild_job",
    ):
        monkeypatch.setattr(background_jobs, name, lambda **kw: False)
    monkeypatch.setattr(
        background_jobs,
        "prepare_next_bootstrap_job",
        lambda **kw: SimpleNamespace(candidate=SimpleNamespace(novel_id=7)),
    )

    def fail(_prepared, **_kwargs):
        stop.set()
        raise RuntimeError("controlled runner failure")

    monkeypatch.setattr(background_jobs, "execute_bootstrap_worker_job", fail)
    with pytest.raises(RuntimeError, match="controlled runner failure"):
        background_jobs.run_worker_loop(stop_event=stop)


def test_cpu_failure_preserves_primary_error_and_observes_model_failure(
    monkeypatch, caplog
):
    _configure_worker(monkeypatch)
    model_started = threading.Event()
    release_model = threading.Event()

    def ingest(*, excluded_novel_ids, **_kwargs):
        if excluded_novel_ids:
            assert model_started.wait(2)
            release_model.set()
            raise ValueError("primary CPU failure")
        return False

    def model_job(_prepared, **_kwargs):
        model_started.set()
        assert release_model.wait(2)
        raise RuntimeError("secondary model failure")

    monkeypatch.setattr(background_jobs, "run_next_novel_ingest_job", ingest)
    for name in (
        "enqueue_next_deferred_window_index_build",
        "run_next_window_index_rebuild_job",
    ):
        monkeypatch.setattr(background_jobs, name, lambda **kw: False)
    monkeypatch.setattr(
        background_jobs,
        "prepare_next_bootstrap_job",
        lambda **kw: SimpleNamespace(candidate=SimpleNamespace(novel_id=7)),
    )
    monkeypatch.setattr(background_jobs, "execute_bootstrap_worker_job", model_job)
    with pytest.raises(ValueError, match="primary CPU failure"):
        background_jobs.run_worker_loop()
    assert "secondary model failure" in caplog.text


@pytest.mark.parametrize("kind", ["ingest", "index"])
def test_cpu_job_selection_skips_reserved_novel_without_blocking_queue(tmp_path, kind):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database import Base
    from app.models import DerivedAssetJob, Novel, NovelIngestJob
    from app.core.ingest.job_store import select_next_novel_ingest_job_novel_id
    from app.core.indexing.lifecycle import (
        select_next_window_index_rebuild_job_novel_id,
    )

    engine = create_engine(f"sqlite:///{tmp_path / 'queue.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    try:
        with factory() as db:
            for novel_id in (7, 8):
                db.add(Novel(id=novel_id, title=str(novel_id), file_path="fixture.txt"))
                db.add(NovelIngestJob(novel_id=novel_id, status="queued"))
                db.add(
                    DerivedAssetJob(
                        novel_id=novel_id,
                        asset_kind="window_index",
                        status="queued",
                        target_revision=3,
                    )
                )
            db.commit()
        select = (
            select_next_novel_ingest_job_novel_id
            if kind == "ingest"
            else select_next_window_index_rebuild_job_novel_id
        )
        assert select(session_factory=factory) == 7
        assert select(session_factory=factory, excluded_novel_ids=(7,)) == 8
        assert select(session_factory=factory, excluded_novel_ids=(7, 8)) is None
        # Releasing the reservation restores the oldest queued job.
        assert select(session_factory=factory) == 7
    finally:
        engine.dispose()
