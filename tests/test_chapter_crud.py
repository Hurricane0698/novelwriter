"""Tests for Chapter CRUD endpoints (Phase 3)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.core.indexing import mark_window_index_build_succeeded
from app.database import Base, get_db
from app.models import Chapter, Novel

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _run_window_index_jobs(*, max_rounds: int = 5) -> None:
    from app.core.indexing import run_next_window_index_rebuild_job

    for _ in range(max_rounds):
        if not run_next_window_index_rebuild_job(session_factory=TestingSessionLocal):
            return
    raise AssertionError("window-index worker did not go idle in time")


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def novel(db):
    n = Novel(title="测试小说", author="测试", file_path="/tmp/test.txt", total_chapters=2)
    db.add(n)
    db.commit()
    db.refresh(n)
    db.add_all([
        Chapter(novel_id=n.id, chapter_number=1, title="第一章", content="内容一"),
        Chapter(novel_id=n.id, chapter_number=2, title="第二章", content="内容二"),
    ])
    db.commit()
    return n


@pytest.fixture
def client(db):
    from app.api import novels
    from app.core.auth import get_current_user
    from app.models import User

    test_app = FastAPI()
    test_app.include_router(novels.router)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_current_user] = lambda: User(
        id=1, username="t", hashed_password="x", role="admin", is_active=True
    )

    with TestClient(test_app) as c:
        yield c
    test_app.dependency_overrides.clear()


class TestCreateChapter:
    def test_create_chapter(self, client, db, novel):
        resp = client.post(
            f"/api/novels/{novel.id}/chapters",
            json={"chapter_number": 3, "title": "第三章", "content": "内容三"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["chapter_number"] == 3
        assert data["title"] == "第三章"
        assert data["source_chapter_label"] is None
        assert data["source_chapter_number"] is None
        assert data["content"] == "内容三"
        assert data["novel_id"] == novel.id
        assert "updated_at" in data

        db.refresh(novel)
        assert novel.total_chapters == 3

    def test_create_chapter_records_chapter_save_event(self, client, novel, monkeypatch):
        from app.api import novel_chapters

        recorded: list[dict[str, object]] = []
        monkeypatch.setattr(
            novel_chapters,
            "record_event",
            lambda db, user_id, event, novel_id=None, meta=None: recorded.append(
                {
                    "user_id": user_id,
                    "event": event,
                    "novel_id": novel_id,
                    "meta": meta,
                }
            ),
        )

        resp = client.post(
            f"/api/novels/{novel.id}/chapters",
            json={"chapter_number": 3, "title": "第三章", "content": "内容三"},
        )

        assert resp.status_code == 201
        assert recorded == [
            {
                "user_id": 1,
                "event": "chapter_save",
                "novel_id": novel.id,
                "meta": {"chapter": 3},
            }
        ]

    def test_create_chapter_auto_number(self, client, db, novel):
        resp = client.post(
            f"/api/novels/{novel.id}/chapters",
            json={"content": "自动内容"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["chapter_number"] == 3  # total_chapters was 2
        assert data["title"] == ""
        assert data["source_chapter_label"] is None
        assert data["source_chapter_number"] is None

        db.refresh(novel)
        assert novel.total_chapters == 3

    def test_create_chapter_auto_number_records_chapter_save_event(self, client, novel, monkeypatch):
        from app.api import novel_chapters

        recorded: list[dict[str, object]] = []
        monkeypatch.setattr(
            novel_chapters,
            "record_event",
            lambda db, user_id, event, novel_id=None, meta=None: recorded.append(
                {
                    "user_id": user_id,
                    "event": event,
                    "novel_id": novel_id,
                    "meta": meta,
                }
            ),
        )

        resp = client.post(
            f"/api/novels/{novel.id}/chapters",
            json={"title": "自动编号章", "content": "自动内容"},
        )

        assert resp.status_code == 201
        assert recorded == [
            {
                "user_id": 1,
                "event": "chapter_save",
                "novel_id": novel.id,
                "meta": {"chapter": 3},
            }
        ]

    def test_create_chapter_auto_number_fills_gap_after_delete(self, client, db, novel):
        # Arrange: chapters 1,2,3 exist.
        db.add(Chapter(novel_id=novel.id, chapter_number=3, title="第三章", content="内容三"))
        novel.total_chapters = 3
        db.commit()

        # Delete chapter 2 -> gap at 2.
        resp = client.delete(f"/api/novels/{novel.id}/chapters/2")
        assert resp.status_code == 204

        db.refresh(novel)
        assert novel.total_chapters == 2

        # Auto-create should fill the smallest missing number (2), not max+1.
        resp = client.post(
            f"/api/novels/{novel.id}/chapters",
            json={"title": "补洞章", "content": "补洞内容"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["chapter_number"] == 2

        db.refresh(novel)
        assert novel.total_chapters == 3

    def test_create_chapter_duplicate_number(self, client, novel):
        resp = client.post(
            f"/api/novels/{novel.id}/chapters",
            json={"chapter_number": 1, "title": "重复", "content": "重复内容"},
        )
        assert resp.status_code == 409

    @pytest.mark.parametrize("line_break", ["\n", "\r"])
    def test_create_chapter_rejects_multiline_title(
        self, client, db, novel, line_break
    ):
        resp = client.post(
            f"/api/novels/{novel.id}/chapters",
            json={
                "chapter_number": 3,
                "title": f"第三章{line_break}越界标题",
                "content": "内容三",
            },
        )

        assert resp.status_code == 422
        assert resp.json()["detail"] == [
            {
                "type": "chapter_title_multiline",
                "loc": ["body", "title"],
                "msg": "Chapter title must be a single line",
                "input": f"第三章{line_break}越界标题",
            }
        ]
        assert (
            db.query(Chapter)
            .filter(Chapter.novel_id == novel.id, Chapter.chapter_number == 3)
            .first()
            is None
        )

    def test_create_markdown_chapter_rejects_structural_heading_in_body(
        self, client, db, novel
    ):
        novel.content_format = "markdown"
        db.commit()

        resp = client.post(
            f"/api/novels/{novel.id}/chapters",
            json={"chapter_number": 3, "title": "第三章", "content": "## 越界章节\n正文"},
        )

        assert resp.status_code == 422
        assert resp.json()["detail"] == {
            "code": "markdown_chapter_body_invalid",
            "message": "Markdown chapter bodies cannot contain H1 or H2 headings",
        }
        assert (
            db.query(Chapter)
            .filter(Chapter.novel_id == novel.id, Chapter.chapter_number == 3)
            .first()
            is None
        )

    def test_get_chapters_meta_preserves_source_metadata(self, client, db, novel):
        db.add(
            Chapter(
                novel_id=novel.id,
                chapter_number=3,
                title="归来",
                source_chapter_label="第844章 归来",
                source_chapter_number=844,
                content="内容三",
            )
        )
        novel.total_chapters = 3
        db.commit()

        resp = client.get(f"/api/novels/{novel.id}/chapters/meta")

        assert resp.status_code == 200
        payload = resp.json()
        chapter_meta = next(item for item in payload if item["chapter_number"] == 3)
        assert chapter_meta["title"] == "归来"
        assert chapter_meta["source_chapter_label"] == "第844章 归来"
        assert chapter_meta["source_chapter_number"] == 844


class TestUpdateChapter:
    def test_update_chapter(self, client, db, novel):
        resp = client.put(
            f"/api/novels/{novel.id}/chapters/1",
            json={"title": "新标题", "content": "新内容"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "新标题"
        assert data["source_chapter_label"] is None
        assert data["source_chapter_number"] is None
        assert data["content"] == "新内容"
        assert data["chapter_number"] == 1

    def test_update_chapter_content_only(self, client, db, novel):
        resp = client.put(
            f"/api/novels/{novel.id}/chapters/1",
            json={"content": "仅更新内容"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "第一章"  # unchanged
        assert data["content"] == "仅更新内容"

    def test_update_chapter_allows_empty_title(self, client, db, novel):
        resp = client.put(
            f"/api/novels/{novel.id}/chapters/1",
            json={"title": ""},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == ""
        assert data["content"] == "内容一"  # unchanged

    @pytest.mark.parametrize("line_break", ["\n", "\r"])
    def test_update_chapter_rejects_multiline_title(
        self, client, db, novel, line_break
    ):
        resp = client.put(
            f"/api/novels/{novel.id}/chapters/1",
            json={"title": f"新标题{line_break}越界标题"},
        )

        assert resp.status_code == 422
        assert resp.json()["detail"] == [
            {
                "type": "chapter_title_multiline",
                "loc": ["body", "title"],
                "msg": "Chapter title must be a single line",
                "input": f"新标题{line_break}越界标题",
            }
        ]
        chapter = (
            db.query(Chapter)
            .filter(Chapter.novel_id == novel.id, Chapter.chapter_number == 1)
            .one()
        )
        assert chapter.title == "第一章"

    def test_update_chapter_empty_payload(self, client, novel):
        resp = client.put(
            f"/api/novels/{novel.id}/chapters/1",
            json={},
        )
        assert resp.status_code == 400

    def test_update_chapter_not_found(self, client, novel):
        resp = client.put(
            f"/api/novels/{novel.id}/chapters/99",
            json={"content": "不存在"},
        )
        assert resp.status_code == 404

    def test_update_markdown_chapter_rejects_structural_heading_in_body(
        self, client, db, novel
    ):
        novel.content_format = "markdown"
        db.commit()

        resp = client.put(
            f"/api/novels/{novel.id}/chapters/1",
            json={"content": "Title\n=====\n正文"},
        )

        assert resp.status_code == 422
        db.refresh(novel)
        chapter = (
            db.query(Chapter)
            .filter(Chapter.novel_id == novel.id, Chapter.chapter_number == 1)
            .one()
        )
        assert chapter.content == "内容一"


class TestDeleteChapter:
    def test_delete_chapter(self, client, db, novel):
        resp = client.delete(f"/api/novels/{novel.id}/chapters/2")
        assert resp.status_code == 204

        db.refresh(novel)
        assert novel.total_chapters == 1

        chapter = (
            db.query(Chapter)
            .filter(Chapter.novel_id == novel.id, Chapter.chapter_number == 2)
            .first()
        )
        assert chapter is None

    def test_delete_chapter_not_found(self, client, novel):
        resp = client.delete(f"/api/novels/{novel.id}/chapters/99")
        assert resp.status_code == 404


class TestWindowIndexLifecycle:
    def _seed_fresh_index(self, db, novel):
        mark_window_index_build_succeeded(
            novel,
            index_payload=b"old-index",
            revision=1,
        )
        db.commit()

    def test_create_chapter_rebuilds_window_index(self, client, db, novel):
        from app.core.indexing import inspect_window_index_rebuild_job

        self._seed_fresh_index(db, novel)

        resp = client.post(
            f"/api/novels/{novel.id}/chapters",
            json={"chapter_number": 3, "title": "第三章", "content": "Alice met Bob again."},
        )

        assert resp.status_code == 201
        db.refresh(novel)
        assert novel.window_index_status == "stale"
        assert novel.window_index_revision == 2
        assert novel.window_index_built_revision == 1
        assert novel.window_index == b"old-index"
        job = inspect_window_index_rebuild_job(db, novel_id=novel.id)
        assert job is not None
        assert job.status == "queued"

        _run_window_index_jobs()

        db.refresh(novel)
        assert novel.window_index_status == "fresh"
        assert novel.window_index_revision == 2
        assert novel.window_index_built_revision == 2
        assert novel.window_index is not None
        assert novel.window_index != b"old-index"
        assert novel.window_index_error is None

    def test_update_chapter_background_failure_marks_window_index_failed(self, client, db, novel, monkeypatch):
        import app.core.indexing.lifecycle as lifecycle_module

        self._seed_fresh_index(db, novel)
        monkeypatch.setattr(
            lifecycle_module,
            "execute_state_proto_build",
            lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
        )

        resp = client.put(
            f"/api/novels/{novel.id}/chapters/1",
            json={"content": "更新后的内容"},
        )

        assert resp.status_code == 200
        db.refresh(novel)
        assert novel.window_index_status == "stale"
        _run_window_index_jobs()
        db.refresh(novel)
        assert novel.window_index_status == "failed"
        assert novel.window_index_revision == 2
        assert novel.window_index_built_revision == 1
        assert novel.window_index is None
        assert novel.window_index_error == "窗口索引重建失败，请稍后重试"

    def test_delete_chapter_rebuilds_window_index(self, client, db, novel):
        from app.core.indexing import inspect_window_index_rebuild_job

        self._seed_fresh_index(db, novel)

        resp = client.delete(f"/api/novels/{novel.id}/chapters/2")

        assert resp.status_code == 204
        db.refresh(novel)
        assert novel.window_index_status == "stale"
        assert novel.window_index_revision == 2
        assert novel.window_index_built_revision == 1
        job = inspect_window_index_rebuild_job(db, novel_id=novel.id)
        assert job is not None
        assert job.status == "queued"

        _run_window_index_jobs()

        db.refresh(novel)
        assert novel.window_index_status == "fresh"
        assert novel.window_index_revision == 2
        assert novel.window_index_built_revision == 2
        assert novel.window_index is not None
        assert novel.window_index_error is None
