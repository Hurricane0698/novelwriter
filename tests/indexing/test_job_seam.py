from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.core.indexing import lifecycle as lifecycle_module
from app.core.indexing import (
    WINDOW_INDEX_STATUS_FAILED,
    WINDOW_INDEX_STATUS_FRESH,
    enqueue_window_index_rebuild_job,
    inspect_window_index_rebuild_job,
    mark_window_index_inputs_changed,
    run_window_index_rebuild_for_latest_revision,
)
from app.database import Base
from app.models import Chapter, DerivedAssetJob, Novel


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _create_novel_with_text(db):
    novel = Novel(title="T", author="A", file_path="/tmp/test.txt")
    db.add(novel)
    db.commit()
    db.refresh(novel)
    db.add(
        Chapter(
            novel_id=novel.id,
            chapter_number=1,
            title="One",
            content="Alice met Bob in the city.",
        )
    )
    db.commit()
    db.refresh(novel)
    return novel


def test_enqueue_window_index_job_coalesces_duplicate_triggers(db):
    novel = _create_novel_with_text(db)

    revision_one = mark_window_index_inputs_changed(novel)
    enqueue_window_index_rebuild_job(
        db,
        novel_id=novel.id,
        target_revision=revision_one,
    )
    db.commit()

    revision_two = mark_window_index_inputs_changed(novel)
    enqueue_window_index_rebuild_job(
        db,
        novel_id=novel.id,
        target_revision=revision_two,
    )
    db.commit()

    jobs = db.query(DerivedAssetJob).all()
    assert len(jobs) == 1
    assert jobs[0].status == "queued"
    assert jobs[0].target_revision == 2
    assert jobs[0].completed_revision is None

    snapshot = inspect_window_index_rebuild_job(db, novel_id=novel.id)
    assert snapshot is not None
    assert snapshot.status == "queued"
    assert snapshot.target_revision == 2


def test_window_index_job_reclaims_stale_running_row(db):
    novel = _create_novel_with_text(db)
    target_revision = mark_window_index_inputs_changed(novel)
    enqueue_window_index_rebuild_job(
        db,
        novel_id=novel.id,
        target_revision=target_revision,
    )
    db.commit()

    job = db.query(DerivedAssetJob).filter(DerivedAssetJob.novel_id == novel.id).first()
    assert job is not None
    stale_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
    job.status = "running"
    job.claimed_revision = target_revision
    job.lease_owner = "stale-owner"
    job.lease_expires_at = stale_time
    job.started_at = stale_time
    db.commit()

    run_window_index_rebuild_for_latest_revision(
        novel.id,
        session_factory=TestingSessionLocal,
    )

    db.refresh(novel)
    db.refresh(job)
    assert novel.window_index_status == WINDOW_INDEX_STATUS_FRESH
    assert novel.window_index_built_revision == target_revision
    assert job.status == "completed"
    assert job.completed_revision == target_revision
    assert job.lease_owner is None
    assert job.lease_expires_at is None


def test_window_index_job_failure_is_recoverable(db, monkeypatch):
    novel = _create_novel_with_text(db)
    target_revision = mark_window_index_inputs_changed(novel)
    enqueue_window_index_rebuild_job(
        db,
        novel_id=novel.id,
        target_revision=target_revision,
    )
    db.commit()

    original_build = lifecycle_module.WINDOW_INDEX_JOB_ADAPTER.build

    def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        lifecycle_module.WINDOW_INDEX_JOB_ADAPTER,
        "build",
        _raise,
    )

    run_window_index_rebuild_for_latest_revision(
        novel.id,
        session_factory=TestingSessionLocal,
    )

    job = db.query(DerivedAssetJob).filter(DerivedAssetJob.novel_id == novel.id).first()
    assert job is not None
    db.refresh(novel)
    assert novel.window_index_status == WINDOW_INDEX_STATUS_FAILED
    assert job.status == "failed"
    assert job.error == "窗口索引重建失败，请稍后重试"

    monkeypatch.setattr(
        lifecycle_module.WINDOW_INDEX_JOB_ADAPTER,
        "build",
        original_build,
    )
    enqueue_window_index_rebuild_job(
        db,
        novel_id=novel.id,
        target_revision=int(novel.window_index_revision or 0),
    )
    db.commit()

    run_window_index_rebuild_for_latest_revision(
        novel.id,
        session_factory=TestingSessionLocal,
    )

    db.refresh(novel)
    db.refresh(job)
    assert novel.window_index_status == WINDOW_INDEX_STATUS_FRESH
    assert novel.window_index_built_revision == target_revision
    assert novel.window_index_error is None
    assert job.status == "completed"
    assert job.completed_revision == target_revision
    assert job.error is None


def test_window_index_job_advances_target_when_inputs_change_mid_build(db, monkeypatch):
    novel = _create_novel_with_text(db)
    target_revision = mark_window_index_inputs_changed(novel)
    enqueue_window_index_rebuild_job(
        db,
        novel_id=novel.id,
        target_revision=target_revision,
    )
    db.commit()

    original_build = lifecycle_module.build_window_index_artifacts
    calls = {"count": 0}

    def _build(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            update_db = TestingSessionLocal()
            try:
                current = update_db.get(Novel, novel.id)
                assert current is not None
                mark_window_index_inputs_changed(current)
                update_db.commit()
            finally:
                update_db.close()
        return original_build(*args, **kwargs)

    monkeypatch.setattr(lifecycle_module, "build_window_index_artifacts", _build)

    run_window_index_rebuild_for_latest_revision(
        novel.id,
        session_factory=TestingSessionLocal,
    )

    job = db.query(DerivedAssetJob).filter(DerivedAssetJob.novel_id == novel.id).first()
    assert job is not None
    db.refresh(novel)
    db.refresh(job)
    assert calls["count"] == 2
    assert novel.window_index_status == WINDOW_INDEX_STATUS_FRESH
    assert novel.window_index_revision == 2
    assert novel.window_index_built_revision == 2
    assert job.status == "completed"
    assert job.target_revision == 2
    assert job.completed_revision == 2
