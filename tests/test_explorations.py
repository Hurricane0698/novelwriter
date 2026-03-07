"""
Tests for Exploration save/restore API.

Validates saving chapter sequences as explorations and restoring them,
per world-model-schema.md spec.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models import Novel, Chapter

pytestmark = pytest.mark.contract


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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
def novel_with_chapters(db):
    """Novel with 5 chapters."""
    n = Novel(title="测试小说", author="测试", file_path="/tmp/test.txt", total_chapters=5)
    db.add(n)
    db.commit()

    for i in range(1, 6):
        db.add(Chapter(
            novel_id=n.id,
            chapter_number=i,
            title=f"第{i}章",
            content=f"第{i}章的内容，这是一段测试文本。",
        ))
    db.commit()
    db.refresh(n)
    return n


@pytest.fixture
def client(db):
    from app.api import world

    test_app = FastAPI()
    test_app.include_router(world.router)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    test_app.dependency_overrides[get_db] = override_get_db

    from app.core.auth import get_current_user
    from app.models import User
    test_app.dependency_overrides[get_current_user] = lambda: User(
        id=1, username="t", hashed_password="x", role="admin", is_active=True
    )

    with TestClient(test_app) as c:
        yield c
    test_app.dependency_overrides.clear()


# ===========================================================================
# Save Exploration
# ===========================================================================

class TestSaveExploration:

    def test_save_chapters_as_exploration(self, client, novel_with_chapters):
        nid = novel_with_chapters.id
        resp = client.post(f"/api/novels/{nid}/explorations", json={
            "name": "暗黑路线",
            "description": "尝试让主角走暗黑路线",
            "from_chapter": 3,
            "to_chapter": 5,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "暗黑路线"
        assert data["from_chapter"] == 3
        assert data["to_chapter"] == 5

    def test_list_explorations(self, client, novel_with_chapters):
        nid = novel_with_chapters.id
        client.post(f"/api/novels/{nid}/explorations", json={
            "name": "路线A", "from_chapter": 1, "to_chapter": 3,
        })
        client.post(f"/api/novels/{nid}/explorations", json={
            "name": "路线B", "from_chapter": 2, "to_chapter": 5,
        })

        resp = client.get(f"/api/novels/{nid}/explorations")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_duplicate_name_409(self, client, novel_with_chapters):
        nid = novel_with_chapters.id
        client.post(f"/api/novels/{nid}/explorations", json={
            "name": "路线A", "from_chapter": 1, "to_chapter": 3,
        })
        resp = client.post(f"/api/novels/{nid}/explorations", json={
            "name": "路线A", "from_chapter": 2, "to_chapter": 4,
        })
        assert resp.status_code == 409


# ===========================================================================
# Restore Exploration
# ===========================================================================

class TestRestoreExploration:

    def test_restore_exploration(self, client, db, novel_with_chapters):
        """Real flow: save → rollback → restore."""
        nid = novel_with_chapters.id

        # 1. Save chapters 3-5 as exploration (before rollback)
        resp = client.post(f"/api/novels/{nid}/explorations", json={
            "name": "暗黑路线", "from_chapter": 3, "to_chapter": 5,
        })
        assert resp.status_code == 201
        xid = resp.json()["id"]

        # 2. Verify original content was captured
        original_ch3 = db.query(Chapter).filter_by(novel_id=nid, chapter_number=3).first().content

        # 3. Rollback: delete chapters 3-5 and write different content
        db.query(Chapter).filter(
            Chapter.novel_id == nid,
            Chapter.chapter_number >= 3,
        ).delete()
        db.commit()
        db.add(Chapter(novel_id=nid, chapter_number=3, title="新第3章", content="完全不同的内容"))
        db.commit()

        # 4. Restore exploration — should bring back original chapters 3-5
        resp = client.post(f"/api/novels/{nid}/explorations/{xid}/restore")
        assert resp.status_code == 200

        # 5. Verify restored content matches original
        restored_ch3 = db.query(Chapter).filter_by(novel_id=nid, chapter_number=3).first().content
        assert restored_ch3 == original_ch3

        total = db.query(Chapter).filter_by(novel_id=nid).count()
        assert total == 5


# ===========================================================================
# Delete Exploration
# ===========================================================================

class TestDeleteExploration:

    def test_delete_exploration(self, client, novel_with_chapters):
        nid = novel_with_chapters.id
        resp = client.post(f"/api/novels/{nid}/explorations", json={
            "name": "临时路线", "from_chapter": 1, "to_chapter": 2,
        })
        xid = resp.json()["id"]

        resp = client.delete(f"/api/novels/{nid}/explorations/{xid}")
        assert resp.status_code == 200

        resp = client.get(f"/api/novels/{nid}/explorations")
        assert len(resp.json()) == 0

    def test_delete_exploration_does_not_affect_main_chapters(self, client, db, novel_with_chapters):
        """Deleting an exploration should not touch main timeline chapters."""
        nid = novel_with_chapters.id
        resp = client.post(f"/api/novels/{nid}/explorations", json={
            "name": "临时路线", "from_chapter": 1, "to_chapter": 3,
        })
        xid = resp.json()["id"]

        client.delete(f"/api/novels/{nid}/explorations/{xid}")

        main_chapters = db.query(Chapter).filter_by(novel_id=nid).count()
        assert main_chapters == 5  # unchanged
