from __future__ import annotations


import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.core.indexing import lifecycle as lifecycle_module
from app.core.cache import invalidate_novel_language_caches
from app.core.indexing import (
    WINDOW_INDEX_REBUILD_FAILED_MESSAGE,
    WINDOW_INDEX_STATUS_FAILED,
    WINDOW_INDEX_STATUS_FRESH,
    WINDOW_INDEX_STATUS_MISSING,
    WINDOW_INDEX_STATUS_STALE,
    enqueue_window_index_rebuild_for_latest_revision,
    mark_window_index_build_succeeded,
    mark_window_index_inputs_changed,
    run_next_window_index_rebuild_job,
)
from app.core.indexing.window_index import NovelIndex
from app.database import Base
from app.models import Chapter, Novel


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


def _enqueue_and_run_latest_revision(novel_id: int) -> None:
    assert (
        enqueue_window_index_rebuild_for_latest_revision(
            novel_id,
            session_factory=TestingSessionLocal,
        )
        is not None
    )
    assert run_next_window_index_rebuild_job(session_factory=TestingSessionLocal) is True


def test_mark_inputs_changed_transitions_fresh_to_stale():
    novel = Novel(title="T", author="A", file_path="/tmp/t.txt")
    mark_window_index_build_succeeded(
        novel,
        index_payload=b"index-bytes",
        revision=1,
    )

    mark_window_index_inputs_changed(novel)

    assert novel.window_index_status == WINDOW_INDEX_STATUS_STALE
    assert novel.window_index_revision == 2
    assert novel.window_index_built_revision == 1
    assert novel.window_index == b"index-bytes"
    assert novel.window_index_error is None


def test_language_invalidation_marks_window_index_stale(db):
    novel = Novel(title="T", author="A", file_path="/tmp/t.txt")
    db.add(novel)
    db.commit()
    db.refresh(novel)
    mark_window_index_build_succeeded(
        novel,
        index_payload=b"index-bytes",
        revision=1,
    )
    db.commit()

    invalidate_novel_language_caches(db, novel.id)

    assert novel.window_index_status == WINDOW_INDEX_STATUS_STALE
    assert novel.window_index_revision == 2
    assert novel.window_index_built_revision == 1
    assert novel.window_index == b"index-bytes"


def test_rebuild_runner_marks_fresh_from_missing_state(db):
    novel = Novel(title="T", author="A", file_path="/tmp/t.txt")
    db.add(novel)
    db.commit()
    db.refresh(novel)
    db.add(Chapter(novel_id=novel.id, chapter_number=1, title="One", content="Alice met Bob in the city."))
    mark_window_index_inputs_changed(novel)
    db.commit()

    _enqueue_and_run_latest_revision(novel.id)

    db.refresh(novel)
    assert novel.window_index_status == WINDOW_INDEX_STATUS_FRESH
    assert novel.window_index_revision == 1
    assert novel.window_index_built_revision == 1
    assert novel.window_index is not None
    assert novel.window_index_error is None


def test_rebuild_runner_marks_failed_on_builder_error(db, monkeypatch):
    novel = Novel(title="T", author="A", file_path="/tmp/t.txt")
    db.add(novel)
    db.commit()
    db.refresh(novel)
    db.add(Chapter(novel_id=novel.id, chapter_number=1, title="One", content="Alice met Bob in the city."))
    mark_window_index_inputs_changed(novel)
    db.commit()

    def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.core.indexing.lifecycle.execute_state_proto_build", _raise)

    _enqueue_and_run_latest_revision(novel.id)

    db.refresh(novel)
    assert novel.window_index_status == WINDOW_INDEX_STATUS_FAILED
    assert novel.window_index_revision == 1
    assert novel.window_index_built_revision is None
    assert novel.window_index is None
    assert novel.window_index_error == WINDOW_INDEX_REBUILD_FAILED_MESSAGE


def test_rebuild_runner_retries_until_latest_revision(db, monkeypatch):
    novel = Novel(title="T", author="A", file_path="/tmp/t.txt")
    db.add(novel)
    db.commit()
    db.refresh(novel)
    db.add(Chapter(novel_id=novel.id, chapter_number=1, title="One", content="Alice met Bob in the city."))
    mark_window_index_inputs_changed(novel)
    db.commit()

    calls = {"count": 0}

    original_build = lifecycle_module.execute_state_proto_build

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

    monkeypatch.setattr("app.core.indexing.lifecycle.execute_state_proto_build", _build)

    _enqueue_and_run_latest_revision(novel.id)

    db.refresh(novel)
    assert calls["count"] == 2
    assert novel.window_index_status == WINDOW_INDEX_STATUS_FRESH
    assert novel.window_index_revision == 2
    assert novel.window_index_built_revision == 2
    assert novel.window_index is not None


def test_rebuild_runner_marks_missing_when_no_chapter_text(db):
    novel = Novel(title="T", author="A", file_path="/tmp/t.txt")
    db.add(novel)
    db.commit()
    db.refresh(novel)
    mark_window_index_inputs_changed(novel)
    db.commit()

    _enqueue_and_run_latest_revision(novel.id)

    db.refresh(novel)
    assert novel.window_index_status == WINDOW_INDEX_STATUS_MISSING
    assert novel.window_index_revision == 1
    assert novel.window_index_built_revision is None
    assert novel.window_index is None


def test_rebuild_runner_persists_state_proto_payload_compatible_with_window_runtime(db):
    novel = Novel(title="T", author="A", file_path="/tmp/t.txt")
    db.add(novel)
    db.commit()
    db.refresh(novel)
    db.add(Chapter(novel_id=novel.id, chapter_number=1, title="One", content="Alice met Bob in the city."))
    mark_window_index_inputs_changed(novel)
    db.commit()

    _enqueue_and_run_latest_revision(novel.id)

    db.refresh(novel)
    restored = NovelIndex.from_msgpack(novel.window_index)
    assert isinstance(restored.find_entity_passages("Alice", limit=1), list)
