import asyncio
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.core.bootstrap import run_bootstrap_job
from app.database import Base, get_db
from app.models import Chapter, Novel, User, WorldEntity, WorldRelationship


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class _FakeAIClient:
    def __init__(self, payload: dict):
        self._payload = payload
        self.calls = 0

    async def generate_structured(self, **kwargs):
        self.calls += 1
        response_model = kwargs["response_model"]
        return response_model.model_validate(self._payload)


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
def client(db, monkeypatch):
    from app.api import world

    captured: dict[str, object] = {}

    def _capture_bootstrap_task(
        job_id: int,
        *,
        session_factory=None,
        client=None,
        user_id: int | None = None,
        llm_config: dict | None = None,
    ):
        # Hosted usage isolation depends on attributing bootstrap LLM calls to the trigger user.
        captured["user_id"] = user_id
        captured["llm_config"] = llm_config

        async def _noop():
            return None

        return _noop()

    def _drop_background_task(coro):
        assert captured.get("user_id") == 1
        coro.close()

        class _DoneTask:
            def done(self):
                return True

        return _DoneTask()

    monkeypatch.setattr(world, "run_bootstrap_job", _capture_bootstrap_task)
    monkeypatch.setattr(world.asyncio, "create_task", _drop_background_task)

    test_app = FastAPI()
    test_app.include_router(world.router)
    test_app.state._bootstrap_task_capture = captured

    def override_get_db():
        try:
            yield db
        finally:
            pass

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[world.get_current_user_or_default] = lambda: User(
        id=1, username="tester", hashed_password="x", role="admin", is_active=True
    )

    with TestClient(test_app) as c:
        yield c
    test_app.dependency_overrides.clear()


def _create_novel_with_text(db) -> Novel:
    novel = Novel(title="Integration Bootstrap", author="Tester", file_path="/tmp/test.txt", total_chapters=1)
    db.add(novel)
    db.commit()
    db.refresh(novel)
    db.add(Chapter(novel_id=novel.id, chapter_number=1, title="One", content=("Alice met Bob in the city. " * 80)))
    db.commit()
    return novel


def test_bootstrap_forwards_byok_headers_to_background_job(client, db):
    novel = _create_novel_with_text(db)

    headers = {
        "x-llm-base-url": "https://example.com/v1",
        "x-llm-api-key": "test-key",
        "x-llm-model": "test-model",
    }
    response = client.post(
        f"/api/novels/{novel.id}/world/bootstrap",
        json={"mode": "initial"},
        headers=headers,
    )
    assert response.status_code == 202

    captured = client.app.state._bootstrap_task_capture
    assert captured["llm_config"] == {
        "base_url": "https://example.com/v1",
        "api_key": "test-key",
        "model": "test-model",
        "billing_source_hint": "selfhost",
    }


def test_reextract_merge_endpoint_and_job_flow(client, db):
    novel = _create_novel_with_text(db)
    confirmed = WorldEntity(
        novel_id=novel.id,
        name="Alice",
        entity_type="Character",
        aliases=["Hero"],
        status="confirmed",
        origin="manual",
    )
    db.add(confirmed)
    db.commit()

    response = client.post(
        f"/api/novels/{novel.id}/world/bootstrap",
        json={"mode": "reextract", "draft_policy": "merge"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["mode"] == "reextract"
    assert body["result"]["index_refresh_only"] is False

    fake_client = _FakeAIClient(
        payload={
            "entities": [
                {"name": "Alice", "entity_type": "Item", "aliases": ["Changed Alias"]},
                {"name": "Bob", "entity_type": "Character", "aliases": ["B"]},
            ],
            "relationships": [{"source_name": "Alice", "target_name": "Bob", "label": "ally"}],
        }
    )
    asyncio.run(run_bootstrap_job(body["job_id"], session_factory=TestingSessionLocal, client=fake_client))

    status = client.get(f"/api/novels/{novel.id}/world/bootstrap/status")
    assert status.status_code == 200
    status_body = status.json()
    assert status_body["status"] == "completed"
    assert status_body["mode"] == "reextract"
    assert status_body["result"]["index_refresh_only"] is False

    db.expire_all()
    refreshed_confirmed = db.query(WorldEntity).filter(WorldEntity.id == confirmed.id).first()
    assert refreshed_confirmed.status == "confirmed"
    assert refreshed_confirmed.origin == "manual"
    assert refreshed_confirmed.entity_type == "Character"
    assert refreshed_confirmed.aliases == ["Hero"]

    bob = db.query(WorldEntity).filter(WorldEntity.novel_id == novel.id, WorldEntity.name == "Bob").first()
    assert bob is not None
    assert bob.status == "draft"
    assert bob.origin == "bootstrap"

    ally = db.query(WorldRelationship).filter(WorldRelationship.novel_id == novel.id, WorldRelationship.label == "ally").first()
    assert ally is not None
    assert ally.status == "draft"
    assert ally.origin == "bootstrap"
    assert fake_client.calls == 1


def test_reextract_replace_force_cleans_bootstrap_drafts(client, db):
    novel = _create_novel_with_text(db)
    confirmed = WorldEntity(
        novel_id=novel.id,
        name="Alice",
        entity_type="Character",
        aliases=["Hero"],
        status="confirmed",
        origin="manual",
    )
    manual_draft = WorldEntity(
        novel_id=novel.id,
        name="ManualDraft",
        entity_type="Location",
        aliases=[],
        status="draft",
        origin="manual",
        created_at=datetime(2026, 2, 19, 0, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 2, 19, 0, 0, 0, tzinfo=timezone.utc),
    )
    old_bootstrap = WorldEntity(
        novel_id=novel.id,
        name="OldBootstrapDraft",
        entity_type="Faction",
        aliases=["Old Alias"],
        status="draft",
        origin="bootstrap",
    )
    db.add_all([confirmed, manual_draft, old_bootstrap])
    db.commit()
    db.refresh(confirmed)
    db.refresh(manual_draft)
    db.refresh(old_bootstrap)

    db.add_all(
        [
            WorldRelationship(
                novel_id=novel.id,
                source_id=confirmed.id,
                target_id=old_bootstrap.id,
                label="old-bootstrap",
                status="draft",
                origin="bootstrap",
            ),
            WorldRelationship(
                novel_id=novel.id,
                source_id=confirmed.id,
                target_id=manual_draft.id,
                label="manual-link",
                status="draft",
                origin="manual",
            ),
        ]
    )
    db.commit()

    response = client.post(
        f"/api/novels/{novel.id}/world/bootstrap",
        json={
            "mode": "reextract",
            "draft_policy": "replace_bootstrap_drafts",
            "force": True,
        },
    )
    assert response.status_code == 202
    body = response.json()
    assert body["mode"] == "reextract"

    fake_client = _FakeAIClient(
        payload={
            "entities": [
                {"name": "Alice", "entity_type": "Item", "aliases": ["Changed Alias"]},
                {"name": "Bob", "entity_type": "Character", "aliases": ["B"]},
            ],
            "relationships": [{"source_name": "Alice", "target_name": "Bob", "label": "ally"}],
        }
    )
    asyncio.run(run_bootstrap_job(body["job_id"], session_factory=TestingSessionLocal, client=fake_client))

    status = client.get(f"/api/novels/{novel.id}/world/bootstrap/status")
    assert status.status_code == 200
    assert status.json()["status"] == "completed"

    db.expire_all()
    entities = db.query(WorldEntity).filter(WorldEntity.novel_id == novel.id).all()
    relationships = db.query(WorldRelationship).filter(WorldRelationship.novel_id == novel.id).all()
    entities_by_name = {entity.name: entity for entity in entities}
    labels = {relationship.label for relationship in relationships}

    assert "OldBootstrapDraft" not in entities_by_name
    assert "ManualDraft" in entities_by_name
    assert entities_by_name["Alice"].status == "confirmed"
    assert entities_by_name["Alice"].origin == "manual"
    assert entities_by_name["Alice"].entity_type == "Character"
    assert entities_by_name["Alice"].aliases == ["Hero"]
    assert entities_by_name["Bob"].status == "draft"
    assert entities_by_name["Bob"].origin == "bootstrap"

    assert "old-bootstrap" not in labels
    assert "manual-link" in labels
    assert "ally" in labels
    assert fake_client.calls == 1
