"""Tests for Chapter CRUD endpoints (Phase 3)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
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
        assert data["content"] == "内容三"
        assert data["novel_id"] == novel.id
        assert "updated_at" in data

        db.refresh(novel)
        assert novel.total_chapters == 3

    def test_create_chapter_auto_number(self, client, db, novel):
        resp = client.post(
            f"/api/novels/{novel.id}/chapters",
            json={"title": "自动编号章", "content": "自动内容"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["chapter_number"] == 3  # total_chapters was 2

        db.refresh(novel)
        assert novel.total_chapters == 3

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


class TestUpdateChapter:
    def test_update_chapter(self, client, db, novel):
        resp = client.put(
            f"/api/novels/{novel.id}/chapters/1",
            json={"title": "新标题", "content": "新内容"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "新标题"
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

    def test_update_chapter_title_only(self, client, db, novel):
        resp = client.put(
            f"/api/novels/{novel.id}/chapters/1",
            json={"title": "仅更新标题"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "仅更新标题"
        assert data["content"] == "内容一"  # unchanged

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
