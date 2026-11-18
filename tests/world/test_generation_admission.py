from unittest.mock import AsyncMock
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.database import Base, get_db
from app.models import Novel, User, WorldGenerationRun


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _settings(**overrides) -> Settings:
    return Settings(
        openai_base_url="https://example.com/v1",
        openai_api_key="test-key",
        openai_model="test-model",
        _env_file=None,
        **overrides,
    )


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
def user(db):
    user = User(
        username="user",
        hashed_password="x",
        role="admin",
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def novel(db, user):
    n = Novel(
        title="测试小说",
        author="测试作者",
        file_path="/tmp/test.txt",
        total_chapters=1,
        owner_id=user.id,
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


@pytest.fixture
def client(db, user):
    from app.api import world
    from app.core.auth import get_current_user_or_default

    test_app = FastAPI()
    test_app.include_router(world.router)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_current_user_or_default] = lambda: user

    with TestClient(test_app) as c:
        yield c
    test_app.dependency_overrides.clear()


def test_generate_world_returns_llm_unavailable_503(client, db, user, novel, monkeypatch):
    from app.core.world import generation_application as generation_app
    from app.core.ai_client import LLMUnavailableError

    mock = AsyncMock(side_effect=LLMUnavailableError("boom"))
    monkeypatch.setattr(generation_app, "generate_world_drafts", mock)

    resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "这是一段足够长的世界观设定文本。"})
    assert resp.status_code == 503


def test_generate_world_returns_busy_semaphore_503(client, db, user, novel, monkeypatch):
    from app.core.world import generation_application as generation_app

    async def _busy() -> None:
        raise HTTPException(status_code=503, detail="busy", headers={"Retry-After": "1"})

    monkeypatch.setattr(generation_app, "acquire_llm_slot", _busy)

    resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "这是一段足够长的世界观设定文本。"})
    assert resp.status_code == 503
    assert resp.headers["retry-after"] == "1"


def test_generate_world_duplicate_click_fast_fails_before_generation(client, db, user, novel, monkeypatch):
    from app.core.world import generation_application as generation_app

    db.add(
        WorldGenerationRun(
            user_id=user.id,
            novel_id=novel.id,
            claim_token="existing-owner",
            status="running",
        )
    )
    db.commit()

    monkeypatch.setattr(
        generation_app,
        "generate_world_drafts",
        AsyncMock(side_effect=AssertionError("duplicate world generation should not execute")),
    )

    resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "这是一段足够长的世界观设定文本。"})
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "world_generate_duplicate_request"


def test_generate_world_does_not_reclaim_old_running_row_on_timeout(client, db, user, novel, monkeypatch):
    import app.config as config_mod
    from app.core.world import generation_application as generation_app

    stale_started = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=10)
    db.add(
        WorldGenerationRun(
            user_id=user.id,
            novel_id=novel.id,
            claim_token="stale-owner",
            status="running",
            created_at=stale_started,
            updated_at=stale_started,
        )
    )
    db.commit()

    prev = config_mod._settings_instance
    config_mod._settings_instance = _settings(
        generation_run_stale_timeout_seconds=1,
    )
    try:
        monkeypatch.setattr(
            generation_app,
            "generate_world_drafts",
            AsyncMock(side_effect=AssertionError("timeout alone must not reclaim a live world-generation run")),
        )

        resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "这是一段足够长的世界观设定文本。"})
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "world_generate_duplicate_request"

    finally:
        config_mod._settings_instance = prev
