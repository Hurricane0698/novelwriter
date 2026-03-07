"""
Tests for dashboard aggregation and batch lorebook helpers.

Uses httpx.AsyncClient to exercise the full HTTP stack:
routing, dependency injection, auth, request parsing, response serialization.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Novel, Chapter, LoreEntry
from app.schemas import LoreEntryBatchCreate


SQLALCHEMY_DATABASE_URL = "sqlite://"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def setup_database():
    """Create tables before each test and drop after."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    """Get a test database session."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def override_get_db(db_session):
    """Override get_db so the app uses the test database."""
    app.dependency_overrides[get_db] = lambda: db_session
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def sample_novel(db_session):
    """Create a sample novel with chapters."""
    novel = Novel(
        title="测试小说",
        author="测试作者",
        file_path="/tmp/test.txt",
        total_chapters=10,
    )
    db_session.add(novel)
    db_session.commit()
    db_session.refresh(novel)

    for i in range(1, 11):
        chapter = Chapter(
            novel_id=novel.id,
            chapter_number=i,
            title=f"第{i}章",
            content=f"这是第{i}章的内容。" * 100,
        )
        db_session.add(chapter)
    db_session.commit()

    return novel


@pytest_asyncio.fixture
async def client():
    """Async HTTP client wired to the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestDashboardEndpoint:
    """Tests for dashboard aggregation via HTTP."""

    async def test_dashboard_basic(self, client, sample_novel):
        resp = await client.get(f"/api/novels/{sample_novel.id}/dashboard")

        assert resp.status_code == 200
        data = resp.json()
        assert data["novel_id"] == sample_novel.id
        assert data["title"] == "测试小说"
        assert data["author"] == "测试作者"
        assert data["total_chapters"] == 10

    async def test_dashboard_with_lorebook(self, client, db_session, sample_novel):
        lore_entry = LoreEntry(
            novel_id=sample_novel.id,
            uid="test-uid-001",
            title="顾慎为",
            content="龙王，原金鹏堡杀手",
            entry_type="Character",
            priority=1,
            enabled=True,
        )
        db_session.add(lore_entry)
        db_session.commit()

        resp = await client.get(f"/api/novels/{sample_novel.id}/dashboard")

        assert resp.status_code == 200
        status = resp.json()["status"]
        assert status["lorebook"]["ready"] is True
        assert status["lorebook"]["count"] == 1
        assert set(status.keys()) == {"lorebook"}

    async def test_dashboard_recent_chapters_limit(self, client, sample_novel):
        resp = await client.get(
            f"/api/novels/{sample_novel.id}/dashboard",
            params={"recent_chapters_limit": 3},
        )

        assert resp.status_code == 200
        assert len(resp.json()["recent_chapters"]) == 3

    async def test_dashboard_novel_not_found(self, client):
        resp = await client.get("/api/novels/99999/dashboard")

        assert resp.status_code == 404
        assert "99999" in resp.json()["detail"]


class TestBatchLorebookEndpoint:
    """Tests for batch lorebook creation via HTTP."""

    async def test_batch_create_lorebook_single(self, client, sample_novel):
        resp = await client.post(
            f"/api/novels/{sample_novel.id}/lorebook/entries/batch",
            json={
                "entries": [
                    {
                        "title": "测试角色",
                        "content": "这是一个测试角色",
                        "entry_type": "Character",
                        "token_budget": 500,
                        "priority": 10,
                        "keywords": [
                            {"keyword": "测试", "is_regex": False, "case_sensitive": False}
                        ],
                    }
                ]
            },
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["created"] == 1
        assert len(data["entries"]) == 1
        assert data["errors"] == []
        assert data["entries"][0]["title"] == "测试角色"

    async def test_batch_create_lorebook_multiple(self, client, sample_novel):
        resp = await client.post(
            f"/api/novels/{sample_novel.id}/lorebook/entries/batch",
            json={
                "entries": [
                    {
                        "title": "角色A",
                        "content": "角色A的描述",
                        "entry_type": "Character",
                        "token_budget": 500,
                        "priority": 1,
                        "keywords": [{"keyword": "角色A", "is_regex": False, "case_sensitive": True}],
                    },
                    {
                        "title": "地点B",
                        "content": "地点B的描述",
                        "entry_type": "Location",
                        "token_budget": 300,
                        "priority": 50,
                        "keywords": [{"keyword": "地点B", "is_regex": False, "case_sensitive": True}],
                    },
                    {
                        "title": "物品C",
                        "content": "物品C的描述",
                        "entry_type": "Item",
                        "token_budget": 200,
                        "priority": 80,
                        "keywords": [{"keyword": "物品C", "is_regex": False, "case_sensitive": True}],
                    },
                ]
            },
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["created"] == 3
        assert len(data["entries"]) == 3

    async def test_batch_create_lorebook_empty(self):
        with pytest.raises(ValidationError):
            LoreEntryBatchCreate.model_validate({"entries": []})

    async def test_batch_create_lorebook_novel_not_found(self, client):
        resp = await client.post(
            "/api/novels/99999/lorebook/entries/batch",
            json={
                "entries": [
                    {
                        "title": "测试",
                        "content": "测试",
                        "entry_type": "Character",
                        "keywords": [{"keyword": "测试", "is_regex": False, "case_sensitive": False}],
                    }
                ]
            },
        )

        assert resp.status_code == 404
        assert "99999" in resp.json()["detail"]
