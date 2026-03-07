"""
Tests for Lorebook API endpoints.
"""

import pytest
import json
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.api import lorebook
from app.models import Novel, LoreEntry, LoreKey
from app.core.lore_manager import LoreManager


# Create engine with StaticPool for in-memory SQLite to work with TestClient
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """Create tables and provide a session for testing."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session):
    """Create a test client with overridden database dependency."""
    test_app = FastAPI()
    test_app.include_router(lorebook.router)

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    test_app.dependency_overrides[get_db] = override_get_db

    from app.core.auth import get_current_user
    from app.models import User as UserModel
    test_app.dependency_overrides[get_current_user] = lambda: UserModel(id=1, username="t", hashed_password="x", role="admin", is_active=True)

    with TestClient(test_app) as client:
        yield client
    test_app.dependency_overrides.clear()


@pytest.fixture
def novel(db_session):
    """Create a test novel."""
    novel = Novel(
        title="Test Novel",
        author="Test Author",
        file_path="/test/path.txt",
        total_chapters=10,
    )
    db_session.add(novel)
    db_session.commit()
    db_session.refresh(novel)
    return novel


@pytest.fixture
def lore_entry(db_session, novel):
    """Create a test lore entry."""
    entry = LoreEntry(
        novel_id=novel.id,
        uid=LoreManager.generate_uid(),
        title="Test Character",
        content="A brave warrior.",
        entry_type="Character",
        token_budget=200,
        priority=1,
        enabled=True,
    )
    db_session.add(entry)
    db_session.flush()

    key = LoreKey(
        entry_id=entry.id,
        keyword="test character",
        is_regex=False,
        case_sensitive=False,
    )
    db_session.add(key)
    db_session.commit()
    db_session.refresh(entry)
    return entry


class TestLorebookAPI:
    """Tests for Lorebook API endpoints."""

    def test_list_entries_empty(self, client, novel):
        """Test listing entries when none exist."""
        response = client.get(f"/api/novels/{novel.id}/lorebook/entries")

        assert response.status_code == 200
        assert response.json() == []

    def test_list_entries(self, client, novel, lore_entry):
        """Test listing entries."""
        response = client.get(f"/api/novels/{novel.id}/lorebook/entries")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["title"] == "Test Character"

    def test_list_entries_enabled_only(self, client, db_session, novel, lore_entry):
        """Test listing only enabled entries."""
        lore_entry.enabled = False
        db_session.commit()

        response = client.get(f"/api/novels/{novel.id}/lorebook/entries?enabled_only=true")

        assert response.status_code == 200
        assert response.json() == []

    def test_create_entry(self, client, novel):
        """Test creating a new entry."""
        entry_data = {
            "title": "New Character",
            "content": "A mysterious figure.",
            "entry_type": "Character",
            "token_budget": 300,
            "priority": 10,
            "keywords": [
                {"keyword": "new character", "is_regex": False, "case_sensitive": False}
            ]
        }

        response = client.post(
            f"/api/novels/{novel.id}/lorebook/entries",
            json=entry_data
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "New Character"
        assert data["token_budget"] == 300
        assert len(data["keywords"]) == 1

    def test_create_entry_no_keywords(self, client, novel):
        """Test creating entry without keywords fails."""
        entry_data = {
            "title": "No Keywords",
            "content": "This should fail.",
            "entry_type": "Character",
            "keywords": []
        }

        response = client.post(
            f"/api/novels/{novel.id}/lorebook/entries",
            json=entry_data
        )

        assert response.status_code == 400
        assert "keyword" in response.json()["detail"].lower()

    def test_create_entry_invalid_novel(self, client):
        """Test creating entry for non-existent novel."""
        entry_data = {
            "title": "Test",
            "content": "Test",
            "entry_type": "Character",
            "keywords": [{"keyword": "test"}]
        }

        response = client.post("/api/novels/9999/lorebook/entries", json=entry_data)

        assert response.status_code == 404

    def test_get_entry(self, client, novel, lore_entry):
        """Test getting a specific entry."""
        response = client.get(
            f"/api/novels/{novel.id}/lorebook/entries/{lore_entry.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == lore_entry.id
        assert data["title"] == "Test Character"

    def test_get_entry_not_found(self, client, novel):
        """Test getting non-existent entry."""
        response = client.get(f"/api/novels/{novel.id}/lorebook/entries/9999")

        assert response.status_code == 404

    def test_update_entry(self, client, novel, lore_entry):
        """Test updating an entry."""
        update_data = {
            "title": "Updated Character",
            "priority": 5
        }

        response = client.patch(
            f"/api/novels/{novel.id}/lorebook/entries/{lore_entry.id}",
            json=update_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Character"
        assert data["priority"] == 5
        assert data["content"] == "A brave warrior."

    def test_update_entry_disable(self, client, novel, lore_entry):
        """Test disabling an entry."""
        response = client.patch(
            f"/api/novels/{novel.id}/lorebook/entries/{lore_entry.id}",
            json={"enabled": False}
        )

        assert response.status_code == 200
        assert response.json()["enabled"] is False

    def test_delete_entry(self, client, novel, lore_entry):
        """Test deleting an entry."""
        response = client.delete(
            f"/api/novels/{novel.id}/lorebook/entries/{lore_entry.id}"
        )

        assert response.status_code == 204

        response = client.get(
            f"/api/novels/{novel.id}/lorebook/entries/{lore_entry.id}"
        )
        assert response.status_code == 404

    def test_add_keyword(self, client, novel, lore_entry):
        """Test adding a keyword to an entry."""
        keyword_data = {
            "keyword": "another keyword",
            "is_regex": False,
            "case_sensitive": True
        }

        response = client.post(
            f"/api/novels/{novel.id}/lorebook/entries/{lore_entry.id}/keywords",
            json=keyword_data
        )

        assert response.status_code == 201
        data = response.json()
        assert data["keyword"] == "another keyword"

    def test_delete_keyword(self, client, db_session, novel, lore_entry):
        """Test deleting a keyword."""
        key2 = LoreKey(
            entry_id=lore_entry.id,
            keyword="second keyword",
            is_regex=False,
            case_sensitive=False,
        )
        db_session.add(key2)
        db_session.commit()

        keyword_id = lore_entry.keywords[0].id

        response = client.delete(
            f"/api/novels/{novel.id}/lorebook/entries/{lore_entry.id}/keywords/{keyword_id}"
        )

        assert response.status_code == 204

    def test_delete_last_keyword_fails(self, client, novel, lore_entry):
        """Test that deleting the last keyword fails."""
        keyword_id = lore_entry.keywords[0].id

        response = client.delete(
            f"/api/novels/{novel.id}/lorebook/entries/{lore_entry.id}/keywords/{keyword_id}"
        )

        assert response.status_code == 400
        assert "last keyword" in response.json()["detail"].lower()

    def test_delete_keyword_cross_novel_fails(self, client, db_session, novel, lore_entry):
        """Test that deleting a keyword across novels is not allowed."""
        other_novel = Novel(
            title="Other Novel",
            author="Other Author",
            file_path="/test/other.txt",
            total_chapters=1,
        )
        db_session.add(other_novel)
        db_session.commit()
        db_session.refresh(other_novel)

        keyword_id = lore_entry.keywords[0].id

        response = client.delete(
            f"/api/novels/{other_novel.id}/lorebook/entries/{lore_entry.id}/keywords/{keyword_id}"
        )

        assert response.status_code == 404

    def test_match_and_inject(self, client, novel, lore_entry):
        """Test keyword matching and context injection."""
        response = client.post(
            f"/api/novels/{novel.id}/lorebook/match?text=The test character appeared."
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["matched_entries"]) == 1
        assert data["matched_entries"][0]["title"] == "Test Character"
        assert data["total_tokens"] == 200

    def test_match_no_matches(self, client, novel, lore_entry):
        """Test matching with no keywords found."""
        response = client.post(
            f"/api/novels/{novel.id}/lorebook/match?text=Unrelated text about cooking."
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["matched_entries"]) == 0
        assert data["context"] == ""

    def test_import_character_card_json(self, client, novel):
        """Test importing a JSON character card."""
        card = {"name": "Alice", "description": "A fearless explorer."}
        files = {
            "file": ("alice.json", json.dumps(card), "application/json"),
        }

        response = client.post(
            f"/api/novels/{novel.id}/lorebook/entries/import/character-card",
            files=files,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Alice"
        assert data["entry_type"] == "Character"
        assert any(key["keyword"] == "Alice" for key in data["keywords"])
